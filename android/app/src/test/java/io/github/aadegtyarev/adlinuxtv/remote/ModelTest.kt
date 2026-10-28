package io.github.aadegtyarev.adlinuxtv.remote

import org.junit.Assert.*
import org.junit.Test

class ModelTest {
    private val idA = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    private val idB = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    private fun center(id: String = idA, address: String = "192.168.1.20", port: Int = 8765) =
        Center(id, "Гостиная", Endpoint.parse("http://$address:$port/remote"))

    @Test fun privateEndpointsAndCanonicalOrigins() {
        assertEquals("http://192.168.1.20:8765", Endpoint.parse("192.168.1.20").origin)
        assertEquals("https://10.0.0.5:9000/remote", Endpoint.parse("https://10.0.0.5:9000/remote").remote)
        assertTrue(Endpoint.parse("http://[fd00::1]:8765").origin.startsWith("http://[fd00:"))
        assertEquals("172.16.2.3", Endpoint.parse("172.16.2.3").address)
    }

    @Test fun publicLoopbackMappedAndMalformedEndpointsRejected() {
        listOf("127.0.0.1", "8.8.8.8", "169.254.1.2", "172.32.1.1", "192.168.1.01",
            "http://[::1]", "http://[fe80::1]", "http://[::ffff:192.168.1.1]",
            "file:///remote", "javascript:alert(1)", "http://user:pin@192.168.1.1",
            "http://192.168.1.1/evil", "http://192.168.1.1?token=secret",
            "http://192.168.1.1#fragment", "http://192.168.1.1:0", "http://192.168.1.1:65536",
            "http://192.168.1.1\\evil", "http://192.168.1.1/%0a", "http://192.168.1.1/remote\nx")
            .forEach { raw -> assertThrows(IllegalArgumentException::class.java) { Endpoint.parse(raw) } }
    }

    @Test fun hostnameResolutionMustBeAllPrivateAndPinnedToLiteral() {
        val endpoint = Endpoint.parse("tv.local") { listOf("192.168.1.21", "192.168.1.20") }
        assertEquals("http://192.168.1.20:8765", endpoint.origin)
        assertThrows(IllegalArgumentException::class.java) {
            Endpoint.parse("tv.local") { listOf("192.168.1.20", "8.8.8.8") }
        }
        assertThrows(IllegalArgumentException::class.java) { Endpoint.parse("unknown.local") }
    }

    @Test fun profileIsolationIncludesDeviceAndOriginNotJustIpCookieScope() {
        val first = center()
        assertEquals(first.profile, center().profile)
        assertNotEquals(first.profile, center(idB).profile)
        assertNotEquals(first.profile, center(port = 8766).profile)
        assertNotEquals(first.profile, center(address = "192.168.1.21").profile)
        assertTrue(first.profile.matches(Regex("tv_[0-9a-f]{64}")))
    }

    @Test fun identityAndNameMetadataBounded() {
        assertThrows(IllegalArgumentException::class.java) { center("not-id") }
        assertThrows(IllegalArgumentException::class.java) { Center(idA, "bad\nname", center().endpoint) }
        assertThrows(IllegalArgumentException::class.java) { Center(idA, "🙂".repeat(41), center().endpoint) }
        assertThrows(IllegalArgumentException::class.java) { Endpoint("http", "8.8.8.8", 8765) }
    }

    @Test fun switchAndSwitchBackNeverAcceptOldCallbacks() {
        val selection = Selection()
        val old = selection.select(center())
        assertTrue(selection.accepts(old))
        val other = selection.select(center(idB))
        assertFalse(selection.accepts(old)); assertTrue(selection.accepts(other))
        val again = selection.select(center())
        assertFalse(selection.accepts(old)); assertFalse(selection.accepts(other))
        assertTrue(selection.accepts(again))
        selection.revoke(); assertFalse(selection.accepts(again)); assertNull(selection.target())
    }

    @Test fun lostDeviceDoesNotSelectAnotherAndDuplicateIdIsAmbiguous() {
        val directory = Directory()
        directory.observe("one", center())
        directory.observe("other", center(idB))
        assertEquals(center(), directory.rediscovered(idA))
        directory.lost("one")
        assertNull(directory.rediscovered(idA))
        directory.observe("new-ip", center(address = "192.168.1.21"))
        assertEquals("192.168.1.21", directory.rediscovered(idA)?.endpoint?.address)
        directory.observe("duplicate", center())
        assertTrue(directory.ambiguous(idA)); assertNull(directory.rediscovered(idA))
    }

    @Test fun directoryBoundsUntrustedAnnouncements() {
        val directory = Directory()
        repeat(100) { index -> directory.observe("service-$index", center()) }
        assertThrows(IllegalArgumentException::class.java) { directory.observe("x".repeat(257), center()) }
        assertEquals(1, directory.centers().size)
        directory.clear(); assertTrue(directory.centers().isEmpty())
    }

    @Test fun newAddressReplacesOldSavedListingButNeverMixesProfiles() {
        val saved = center()
        val updated = center(address = "192.168.1.21")
        assertEquals(listOf(updated), pickerCenters(listOf(updated), listOf(saved)))
        assertNotEquals(saved.profile, updated.profile)
        assertEquals(2, pickerCenters(listOf(updated, saved), listOf(saved)).size)
    }

    @Test fun staleServiceIntentCannotRetireValidNewOwner() {
        val selection = Selection()
        val old = selection.select(center())
        val current = selection.select(center(idB))
        assertTrue(retireStaleService(old, current))
        assertFalse(retireStaleService(current, current))
        assertTrue(retireStaleService(old, null))
        assertTrue(retireStaleService(null, current))
    }

    @Test fun pendingPlaybackNeverConfirmsDifferentOrUnavailableMedia() {
        val wanted = PendingPlayback(false, 5000, "a".repeat(32))
        assertTrue(wanted.sameSource(Playback(true, mediaId = "a".repeat(32))))
        assertFalse(wanted.sameSource(Playback(true, playing = false, mediaId = "b".repeat(32))))
        assertFalse(wanted.sameSource(Playback(false)))
        assertFalse(wanted.sameSource(Playback(true)))
    }

    @Test fun startupUsesOnlySavedLastOriginAndHonorsExplicitPicker() {
        val last = center()
        val other = center(idB)
        assertEquals(last, startupCenter(listOf(other, last), last.id, false))
        assertNull(startupCenter(listOf(other), last.id, false))
        assertNull(startupCenter(listOf(last), null, false))
        assertNull(startupCenter(listOf(last), last.id, true))
    }

    @Test fun remoteMediaCapabilitiesAreExplicitNotToggle() {
        val playing = Playback(true, playing = true, canPlay = true, canPause = true)
        assertTrue(playing.permits("pause")); assertTrue(playing.permits("play"))
        assertFalse(playing.permits("toggle")); assertFalse(playing.permits("next"))
        assertFalse(Playback(false, canPlay = true).permits("play"))
    }
}

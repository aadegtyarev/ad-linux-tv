package io.github.aadegtyarev.adlinuxtv.remote

import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.os.Looper
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.mockito.kotlin.any
import org.mockito.kotlin.doAnswer
import org.mockito.kotlin.mock
import org.mockito.kotlin.whenever
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.LooperMode
import java.net.InetAddress
import java.time.Duration

/** Fake NSD and virtual Android Looper. No platform discovery, device, network or WebView. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28], manifest = Config.NONE)
@LooperMode(LooperMode.Mode.PAUSED)
class DiscoveryTest {
    private lateinit var manager: NsdManager
    private lateinit var discovery: Discovery
    private val listeners = mutableListOf<NsdManager.DiscoveryListener>()
    private val resolvers = mutableListOf<NsdManager.ResolveListener>()
    private val updates = mutableListOf<Pair<List<Center>, String>>()

    @Before fun setup() {
        manager = mock()
        doAnswer { call -> listeners.add(call.getArgument(2)); null }
            .whenever(manager).discoverServices(any<String>(), any<Int>(), any<NsdManager.DiscoveryListener>())
        doAnswer { call -> resolvers.add(call.getArgument(1)); null }
            .whenever(manager).resolveService(any<NsdServiceInfo>(), any<NsdManager.ResolveListener>())
        discovery = Discovery(manager) { centers, message -> updates.add(centers to message) }
    }
    private fun idle() = shadowOf(Looper.getMainLooper()).idle()
    private fun info(name: String = "test-service", address: String = "192.168.1.20", protocol: String = "1") =
        NsdServiceInfo().apply {
            serviceName = name; serviceType = "_ad-linux-tv._tcp."
            host = InetAddress.getByName(address); port = 8765
            setAttribute("id", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
            setAttribute("name", "Гостиная"); setAttribute("protocol", protocol); setAttribute("path", "/remote")
        }

    @Test fun stoppedGenerationAndLateResolveCannotPublishOrRepopulate() {
        discovery.start()
        val old = listeners.last()
        old.onServiceFound(info()); idle()
        assertEquals(1, resolvers.size)
        discovery.stop()
        resolvers[0].onServiceResolved(info()); idle()
        assertTrue(updates.none { it.first.isNotEmpty() })
        discovery.start()
        old.onServiceFound(info()); idle()
        assertEquals(1, resolvers.size)
        listeners.last().onServiceFound(info()); idle()
        resolvers.last().onServiceResolved(info()); idle()
        assertEquals(1, updates.last().first.size)
    }

    @Test fun lostThenRefoundNameDiscardsOldResolutionButAcceptsNewObservation() {
        discovery.start()
        val observer = listeners.last()
        observer.onServiceFound(info()); idle()
        val old = resolvers[0]
        observer.onServiceLost(info()); observer.onServiceFound(info()); idle()
        old.onServiceResolved(info()); idle()
        assertTrue(updates.last().first.isEmpty())
        assertEquals(2, resolvers.size)
        resolvers[1].onServiceResolved(info(address = "192.168.1.21")); idle()
        assertEquals("192.168.1.21", updates.last().first.single().endpoint.address)
        old.onServiceResolved(info()); idle()
        assertEquals("192.168.1.21", updates.last().first.single().endpoint.address)
    }

    @Test fun obsoleteQueuedResolutionCannotPublishAfterNewerSameNameObservation() {
        discovery.start()
        val observer = listeners.last()
        observer.onServiceFound(info()); observer.onServiceFound(info()); idle()
        resolvers[0].onServiceResolved(info()); idle()
        assertTrue(updates.last().first.isEmpty())
        resolvers[1].onServiceResolved(info(address = "192.168.1.21")); idle()
        assertEquals("192.168.1.21", updates.last().first.single().endpoint.address)
    }

    @Test fun stalledResolverStopsSchedulingUntilExplicitRefreshAndIgnoresLateCallback() {
        discovery.start()
        val old = listeners.last()
        old.onServiceFound(info()); idle()
        shadowOf(Looper.getMainLooper()).idleFor(Duration.ofSeconds(8))
        assertTrue(updates.last().second.contains("Обновить"))
        old.onServiceFound(info("second")); idle()
        assertEquals(1, resolvers.size)
        resolvers[0].onServiceResolved(info()); idle()
        assertTrue(updates.last().first.isEmpty())
        discovery.start()
        listeners.last().onServiceFound(info()); idle()
        assertEquals(2, resolvers.size)
        resolvers.last().onServiceResolved(info()); idle()
        assertEquals(1, updates.last().first.size)
    }

    @Test fun invalidProtocolAndPublicAddressNeverBecomeSelectableCenters() {
        discovery.start()
        val observer = listeners.last()
        observer.onServiceFound(info()); idle()
        resolvers.last().onServiceResolved(info(protocol = "2")); idle()
        assertTrue(updates.last().first.isEmpty())
        observer.onServiceFound(info()); idle()
        resolvers.last().onServiceResolved(info(address = "8.8.8.8")); idle()
        assertTrue(updates.last().first.isEmpty())
    }

    @Test fun untrustedDiscoveryQueueIsBoundedAndResolvedSerially() {
        discovery.start()
        repeat(100) { listeners.last().onServiceFound(info("service-$it")) }
        idle()
        assertEquals(1, resolvers.size)
        repeat(64) { index ->
            assertEquals(index + 1, resolvers.size)
            resolvers[index].onServiceResolved(info("service-$index")); idle()
        }
        assertEquals(64, resolvers.size)
    }
}

package io.github.aadegtyarev.adlinuxtv.remote

import org.junit.Assert.*
import org.junit.Test

class AppInfoTest {
    private val center = Center("12345678-1234-1234-1234-123456789abc", "TV", Endpoint("http", "192.168.1.20", 8765))
    private val target = Target(7, center)
    private val url = center.endpoint.remote + "#device=" + center.id

    @Test fun runtimeValuesAreUsedAndReadOnce() {
        var reads = 0
        val info = AppInfo.read { reads++; "2.7-test" to 42L }
        assertEquals(1, reads)
        assertEquals("2.7-test", info.version)
        assertEquals(42, info.build)
        assertEquals(info.script(), info.script())
        assertEquals(1, reads)
    }

    @Test fun missingInvalidAndFailedMetadataAreHonestAndBounded() {
        for (version in listOf(null, "", "  ", "v".repeat(81), "v\n1", "v\u007f", "v\ud800")) {
            assertEquals("unknown", AppInfo.read { version to 6L }.version)
        }
        assertEquals("v".repeat(80), AppInfo.read { "v".repeat(80) to 6L }.version)
        for (code in listOf(-1L, 0L, Int.MAX_VALUE.toLong() + 1, Long.MAX_VALUE)) {
            assertEquals(0, AppInfo.read { "1.0" to code }.build)
        }
        assertEquals(Int.MAX_VALUE, AppInfo.read { "1.0" to Int.MAX_VALUE.toLong() }.build)
        val failed = AppInfo.read { throw IllegalStateException("private exception details") }
        assertEquals("unknown", failed.version)
        assertEquals(0, failed.build)
        assertFalse(failed.script().contains("private"))
        assertEquals(0, AppInfo.read { null to 0L }.build)
    }

    @Test fun scriptHasOnlyFixedReadOnlyPublicScalarsAndEscapedData() {
        val info = AppInfo.read { "\"'\\</script>\u2028\u2029Ж" to 6L }
        assertEquals(
            "(()=>{if(Object.prototype.hasOwnProperty.call(window,'adLinuxTvAppInfo'))return;" +
                "Object.defineProperty(window,'adLinuxTvAppInfo',{value:Object.freeze({version:\"" +
                "\\u0022\\u0027\\u005c\\u003c\\u002f\\u0073\\u0063\\u0072\\u0069\\u0070\\u0074\\u003e\\u2028\\u2029\\u0416" +
                "\",build:6}),writable:false,configurable:false,enumerable:true});})()",
            info.script())
        assertFalse(info.script().contains("</script>"))
        assertTrue(AppInfo.read { "v".repeat(80) to 6L }.script().length < 800)
    }

    @Test fun injectionRequiresCurrentTargetPageAndTrustedRemoteUrl() {
        assertTrue(AppInfo.mayInject(target, target, true, url, url))
        assertTrue(AppInfo.mayInject(target, target, true, center.endpoint.remote, center.endpoint.remote))
        assertFalse(AppInfo.mayInject(target, null, true, url, url))
        assertFalse(AppInfo.mayInject(target, target.copy(epoch = 8), true, url, url))
        assertFalse(AppInfo.mayInject(target, target.copy(center = center.copy(endpoint = Endpoint("http", "192.168.1.21", 8765))), true, url, url))
        // Activity combines view identity, shown target, lookup generation and live lifecycle here.
        assertFalse(AppInfo.mayInject(target, target, false, url, url))
        assertFalse(AppInfo.mayInject(target, target, true, null, null))
        assertFalse(AppInfo.mayInject(target, target, true, url, null))
        assertFalse(AppInfo.mayInject(target, target, true, url, center.endpoint.remote))
        for (bad in listOf(
            "http://192.168.1.21:8765/remote", "https://192.168.1.20:8765/remote",
            "http://192.168.1.20:8766/remote", "http://user@192.168.1.20:8765/remote",
            "http://192.168.1.20:8765/", "http://192.168.1.20:8765/api/settings",
            "http://192.168.1.20:8765/%72emote", "http://public.example/remote",
            "javascript:alert(1)", "about:blank", "not a URI"
        )) assertFalse(bad, AppInfo.mayInject(target, target, true, bad, bad))
    }
}

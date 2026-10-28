package io.github.aadegtyarev.adlinuxtv.remote

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MediaOptInTest {
    private val center = Center("123e4567-e89b-12d3-a456-426614174000", "TV", Endpoint("http", "192.168.1.2", 8765))
    private val target = Target(1, center)

    @Test fun disabledByDefaultAndOrdinaryStartupNeverConnects() {
        assertFalse(MediaOptIn.mayConnect(false, true, true, target))
        assertFalse(MediaOptIn.mayConnect(true, true, false, target))
    }

    @Test fun permissionDenialDoesNotConnect() {
        assertFalse(MediaOptIn.mayConnect(true, false, true, target))
    }

    @Test fun matchingLiveOwnerSuppressesReconnectButStaleOwnerDoesNot() {
        assertFalse(MediaOptIn.needsConnect(target, target, true))
        assertTrue(MediaOptIn.needsConnect(target, target, false))
        assertTrue(MediaOptIn.needsConnect(target, Target(2, center), true))
    }

    @Test fun startupFailureFeedbackRequiresCurrentOwnerSelectionAndGeneration() {
        assertTrue(MediaOptIn.mayReportStartupFailure(true, true, true))
        assertFalse(MediaOptIn.mayReportStartupFailure(false, true, true))
        assertFalse(MediaOptIn.mayReportStartupFailure(true, false, true))
        assertFalse(MediaOptIn.mayReportStartupFailure(true, true, false))
    }

    @Test fun missingRetiredOrRecreatedSelectionDoesNotConnectUntilCurrentTargetIsReady() {
        assertFalse(MediaOptIn.mayConnect(true, true, true, null))
        val recreated = Target(2, center)
        assertFalse(MediaOptIn.mayConnect(true, true, false, recreated))
        assertTrue(MediaOptIn.mayConnect(true, true, true, recreated))
    }
}

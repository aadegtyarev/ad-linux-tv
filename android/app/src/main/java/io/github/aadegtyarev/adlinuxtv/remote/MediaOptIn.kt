package io.github.aadegtyarev.adlinuxtv.remote

/** Pure opt-in policy: permission denial and unselected targets never authorize a connection. */
object MediaOptIn {
    const val PREFERENCE = "shade_media_enabled"
    fun mayConnect(enabled: Boolean, permissionGranted: Boolean, foreground: Boolean, target: Target?): Boolean =
        enabled && permissionGranted && foreground && target != null

    fun needsConnect(target: Target, owner: Target?, connectionLive: Boolean): Boolean =
        !connectionLive || owner != target

    fun mayReportStartupFailure(ownerMatches: Boolean, selectionCurrent: Boolean, generationCurrent: Boolean): Boolean =
        ownerMatches && selectionCurrent && generationCurrent
}

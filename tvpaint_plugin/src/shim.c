/*
 * Expose TVPaint SDK values that live only in C headers.
 *
 * Constants and 'PIFilter' layout differ between SDK versions and
 * platforms, so Rust reads them from here instead of duplicating them.
 */

#include <string.h>

#include "plugdllx.h"
#include "pikeys.h"

const INTPTR AYON_PIRF_STANDARD_REQ = PIRF_STANDARD_REQ;
const INTPTR AYON_PIRF_HIDDEN_REQ = PIRF_HIDDEN_REQ;
const INTPTR AYON_PIRF_COLLAPSABLE_REQ = PIRF_COLLAPSABLE_REQ;
const INTPTR AYON_FILTERREQ_NO_TBAR = FILTERREQ_NO_TBAR;
const INTPTR AYON_PIRBF_BUTTON_NORMAL = PIRBF_BUTTON_NORMAL;
const INTPTR AYON_PIRBF_BUTTON_ACTION = PIRBF_BUTTON_ACTION;
const int AYON_PITICKS_FLAG_ON = PITICKS_FLAG_ON;

const INTPTR AYON_PICBREQ_OPEN = PICBREQ_OPEN;
const INTPTR AYON_PICBREQ_CLOSE = PICBREQ_CLOSE;
const INTPTR AYON_PICBREQ_BUTTON_UP = PICBREQ_BUTTON_UP;
const INTPTR AYON_PICBREQ_TICKS = PICBREQ_TICKS;

void ayon_set_filter_info(
    PIFilter *filter, const char *name, int version, int revision
) {
    strncpy(filter->PIName, name, sizeof(filter->PIName) - 1);
    filter->PIName[sizeof(filter->PIName) - 1] = '\0';
    filter->PIVersion = version;
    filter->PIRevision = revision;
}

const char *ayon_filter_name(PIFilter *filter) {
    return filter->PIName;
}

int ayon_filter_version(PIFilter *filter) {
    return filter->PIVersion;
}

int ayon_filter_revision(PIFilter *filter) {
    return filter->PIRevision;
}

/*
 * TVPaint host functions used by the plugin.
 *
 * They replace 'dllx.c' (SDK from TVPaint support) and 'pi-private.c'
 * (public SDK), which aren't compiled. Every function passes arguments to
 * TVPaint through 'PIFilter.CallBack' in an 'INTPTR' array, and TVPaint
 * writes results into it, sometimes more values than the function reads.
 * 'pi-private.c' sizes the arrays to the passed arguments, so TVPaint
 * overwrites the stack and crashes (TVPaint 11.7). The arrays here are
 * large enough for any request ('PIRT_INFO' can use up to 32 values).
 *
 * Functions have 'ayon_' prefix, because their signatures differ between
 * SDK headers which declare the original names.
 */

#include <stddef.h>

#ifdef AYON_PUBLIC_SDK
#include "TVPaintAnimationSDK/TVPaintSDK.h"
#include "TVPaintAnimationSDK/pi-private.h"
#else
#include "plugdllx.h"
#include "plugx.h"
#endif

#define AYON_ARG_COUNT 32

static INTPTR ayon_callback(PIFilter *filter, INTPTR command, INTPTR *arg) {
    return filter->CallBack(filter, command, arg);
}

INTPTR ayon_TVOpenReq(
    PIFilter *filter, int width, int height, int x, int y,
    INTPTR flags, const char *name
) {
    INTPTR arg[AYON_ARG_COUNT] = {0};
    arg[0] = width;
    arg[1] = height;
    arg[2] = x;
    arg[3] = y;
    arg[4] = flags;
    arg[5] = (INTPTR)name;
    return ayon_callback(filter, CB_OPENREQ, arg);
}

INTPTR ayon_TVOpenFilterReqEx(
    PIFilter *filter, int width, int height, void *message_fn, void *keys,
    INTPTR req_flags, INTPTR menu_flags
) {
    INTPTR arg[AYON_ARG_COUNT] = {0};
    arg[0] = width;
    arg[1] = height;
    arg[2] = (INTPTR)message_fn;
    arg[3] = (INTPTR)keys;
    arg[4] = req_flags;
    arg[5] = menu_flags;
    return ayon_callback(filter, CB_OPENFILTERREQ, arg);
}

void ayon_TVCloseReq(PIFilter *filter, INTPTR req) {
    INTPTR arg[AYON_ARG_COUNT] = {0};
    arg[0] = req;
    ayon_callback(filter, CB_CLOSEREQ, arg);
}

static int ayon_req_cmd(PIFilter *filter, INTPTR *arg) {
    return (int)ayon_callback(filter, CB_SENDREQCMD, arg);
}

int ayon_TVSetReqTitle(PIFilter *filter, INTPTR req, const char *title) {
    INTPTR arg[AYON_ARG_COUNT] = {0};
    arg[0] = PIRT_NAME;
    arg[1] = req;
    arg[2] = (INTPTR)title;
    return ayon_req_cmd(filter, arg);
}

int ayon_TVReqToFront(PIFilter *filter, INTPTR req) {
    INTPTR arg[AYON_ARG_COUNT] = {0};
    arg[0] = PIRT_FRONT;
    arg[1] = req;
    return ayon_req_cmd(filter, arg);
}

int ayon_TVDisplayReq(PIFilter *filter, INTPTR req, int display) {
    INTPTR arg[AYON_ARG_COUNT] = {0};
    arg[0] = PIRT_DISPLAY_REQ;
    arg[1] = req;
    arg[2] = display;
    return ayon_req_cmd(filter, arg);
}

int ayon_TVInfoReq(
    PIFilter *filter, INTPTR req, int *x, int *y, int *w, int *h
) {
    INTPTR arg[AYON_ARG_COUNT] = {0};
    arg[0] = PIRT_INFO;
    arg[1] = req;
    int result = ayon_req_cmd(filter, arg);
    if (result == 0) {
        return 0;
    }
    if (x) *x = (int)arg[2];
    if (y) *y = (int)arg[3];
    if (w) *w = (int)arg[4];
    if (h) *h = (int)arg[5];
    return result;
}

int ayon_TVResizeReq(
    PIFilter *filter, INTPTR req, int x, int y, int w, int h
) {
    INTPTR arg[AYON_ARG_COUNT] = {0};
    arg[0] = PIRT_RESIZE;
    arg[1] = req;
    arg[2] = x;
    arg[3] = y;
    arg[4] = w;
    arg[5] = h;
    return ayon_req_cmd(filter, arg);
}

int ayon_TVGrabTicks(PIFilter *filter, INTPTR req, int flag) {
    INTPTR arg[AYON_ARG_COUNT] = {0};
    arg[0] = PIRT_GRAB_TICKS;
    arg[1] = req;
    arg[2] = flag;
    return ayon_req_cmd(filter, arg);
}

int ayon_TVAddButtonReq(
    PIFilter *filter, INTPTR req, int x, int y, int w, int h, int id,
    INTPTR flags, const char *name
) {
    INTPTR arg[AYON_ARG_COUNT] = {0};
    arg[0] = PIRT_ADD_BUTTON;
    arg[1] = req;
    arg[2] = x;
    arg[3] = y;
    arg[4] = w;
    arg[5] = h;
    arg[6] = id;
    arg[7] = flags;
    arg[8] = (INTPTR)name;
    return ayon_req_cmd(filter, arg);
}

int ayon_TVRemoveButtonReq(PIFilter *filter, INTPTR req, int id) {
    INTPTR arg[AYON_ARG_COUNT] = {0};
    arg[0] = PIRT_REMOVE_BUTTON;
    arg[1] = req;
    arg[2] = id;
    return ayon_req_cmd(filter, arg);
}

int ayon_TVSetButtonInfoText(
    PIFilter *filter, INTPTR req, int id, const char *text
) {
    INTPTR arg[AYON_ARG_COUNT] = {0};
    arg[0] = PIRT_SET_INFO_TEXT;
    arg[1] = req;
    arg[2] = id;
    arg[3] = (INTPTR)text;
    return ayon_req_cmd(filter, arg);
}

void ayon_TVWarning(PIFilter *filter, const char *text) {
    INTPTR arg[AYON_ARG_COUNT] = {0};
    arg[0] = (INTPTR)text;
    ayon_callback(filter, CB_WARNING, arg);
}

int ayon_TVSendCmd(PIFilter *filter, const char *cmd, char *result) {
    INTPTR arg[AYON_ARG_COUNT] = {0};
    arg[0] = (INTPTR)cmd;
    arg[1] = (INTPTR)result;
    return (int)ayon_callback(filter, CB_SENDCMD, arg);
}

int ayon_TVExecute(PIFilter *filter) {
    INTPTR arg[AYON_ARG_COUNT] = {0};
    return (int)ayon_callback(filter, CB_EXECUTE, arg);
}

int ayon_TVReadUserString(
    PIFilter *filter, const char *section, const char *name, char *value,
    const char *def, int max_chars
) {
    INTPTR arg[AYON_ARG_COUNT] = {0};
    arg[0] = (INTPTR)section;
    arg[1] = (INTPTR)name;
    arg[2] = (INTPTR)value;
    arg[3] = (INTPTR)def;
    arg[4] = max_chars;
    return (int)ayon_callback(filter, CB_READ_USER_STRING, arg);
}

int ayon_TVWriteUserString(
    PIFilter *filter, const char *section, const char *name,
    const char *value
) {
    INTPTR arg[AYON_ARG_COUNT] = {0};
    arg[0] = (INTPTR)section;
    arg[1] = (INTPTR)name;
    arg[2] = (INTPTR)value;
    return (int)ayon_callback(filter, CB_WRITE_USER_STRING, arg);
}

//! Bindings to TVPaint SDK host functions compiled from 'dllx.c'.
//!
//! All functions must be called from TVPaint's main thread, i.e. from
//! inside one of the 'PI_*' callbacks.

use std::ffi::{c_char, c_int, c_void, CStr, CString};

/// 'INTPTR' from 'plugdllx.h', a pointer sized integer.
pub type IntPtr = isize;

/// Opaque 'PIFilter' structure owned by TVPaint.
#[repr(C)]
pub struct PIFilter {
    _private: [u8; 0],
}

type MessageFn =
    unsafe extern "system" fn(*mut PIFilter, IntPtr, IntPtr, *mut IntPtr) -> c_int;

extern "C" {
    // Values from 'shim.c'
    pub static AYON_PIRF_STANDARD_REQ: IntPtr;
    pub static AYON_PIRF_HIDDEN_REQ: IntPtr;
    pub static AYON_PIRF_COLLAPSABLE_REQ: IntPtr;
    pub static AYON_FILTERREQ_NO_TBAR: IntPtr;
    pub static AYON_PIRBF_BUTTON_NORMAL: IntPtr;
    pub static AYON_PIRBF_BUTTON_ACTION: IntPtr;
    pub static AYON_PITICKS_FLAG_ON: c_int;

    pub static AYON_PICBREQ_OPEN: IntPtr;
    pub static AYON_PICBREQ_CLOSE: IntPtr;
    pub static AYON_PICBREQ_BUTTON_UP: IntPtr;
    pub static AYON_PICBREQ_TICKS: IntPtr;

    fn ayon_set_filter_info(
        filter: *mut PIFilter,
        name: *const c_char,
        version: c_int,
        revision: c_int,
    );
    fn ayon_filter_name(filter: *mut PIFilter) -> *const c_char;
    fn ayon_filter_version(filter: *mut PIFilter) -> c_int;
    fn ayon_filter_revision(filter: *mut PIFilter) -> c_int;

    // Host functions from 'dllx.c'
    fn TVOpenReq(
        filter: *mut PIFilter,
        width: c_int,
        height: c_int,
        x: c_int,
        y: c_int,
        flags: IntPtr,
        name: *const c_char,
    ) -> IntPtr;
    fn TVOpenFilterReqEx(
        filter: *mut PIFilter,
        width: c_int,
        height: c_int,
        message_fn: Option<MessageFn>,
        keys: *mut c_void,
        req_flags: IntPtr,
        menu_flags: IntPtr,
    ) -> IntPtr;
    fn TVCloseReq(filter: *mut PIFilter, req: IntPtr);
    fn TVSetReqTitle(filter: *mut PIFilter, req: IntPtr, title: *const c_char) -> c_int;
    fn TVReqToFront(filter: *mut PIFilter, req: IntPtr) -> c_int;
    fn TVInfoReq(
        filter: *mut PIFilter,
        req: IntPtr,
        x: *mut c_int,
        y: *mut c_int,
        w: *mut c_int,
        h: *mut c_int,
    ) -> c_int;
    fn TVResizeReq(
        filter: *mut PIFilter,
        req: IntPtr,
        x: c_int,
        y: c_int,
        w: c_int,
        h: c_int,
    ) -> c_int;
    fn TVGrabTicks(filter: *mut PIFilter, req: IntPtr, flag: c_int) -> c_int;
    fn TVAddButtonReq(
        filter: *mut PIFilter,
        req: IntPtr,
        x: c_int,
        y: c_int,
        w: c_int,
        h: c_int,
        id: c_int,
        flags: IntPtr,
        name: *const c_char,
    ) -> c_int;
    fn TVRemoveButtonReq(filter: *mut PIFilter, req: IntPtr, id: c_int) -> c_int;
    fn TVSetButtonInfoText(
        filter: *mut PIFilter,
        req: IntPtr,
        id: c_int,
        text: *const c_char,
    ) -> c_int;
    fn TVWarning(filter: *mut PIFilter, text: *const c_char);
    fn TVSendCmd(filter: *mut PIFilter, cmd: *const c_char, result: *mut c_char) -> c_int;
    fn TVExecute(filter: *mut PIFilter) -> c_int;
    fn TVReadUserString(
        filter: *mut PIFilter,
        section: *const c_char,
        name: *const c_char,
        value: *mut c_char,
        default: *const c_char,
        max_chars: c_int,
    ) -> c_int;
    fn TVWriteUserString(
        filter: *mut PIFilter,
        section: *const c_char,
        name: *const c_char,
        value: *const c_char,
    ) -> c_int;
}

/// Size of buffer for output of george commands.
///
/// The SDK does not document maximum output length, the previous C++
/// plugin used 2048 bytes. Use a much larger buffer to stay on safe side.
const GEORGE_OUTPUT_SIZE: usize = 1 << 16;

/// Convert text to C string, removing NUL bytes which C can't represent.
pub fn c_string(value: &str) -> CString {
    CString::new(value.replace('\0', "")).unwrap_or_default()
}

/// Requester position and size.
pub struct ReqInfo {
    pub x: c_int,
    pub y: c_int,
}

/// Safe wrapper around the 'PIFilter' pointer passed by TVPaint.
#[derive(Clone, Copy)]
pub struct Filter(pub *mut PIFilter);

impl Filter {
    pub fn set_info(&self, name: &str, version: i32, revision: i32) {
        let name = c_string(name);
        unsafe { ayon_set_filter_info(self.0, name.as_ptr(), version, revision) }
    }

    pub fn name(&self) -> String {
        unsafe {
            CStr::from_ptr(ayon_filter_name(self.0))
                .to_string_lossy()
                .into_owned()
        }
    }

    pub fn version(&self) -> (i32, i32) {
        unsafe { (ayon_filter_version(self.0), ayon_filter_revision(self.0)) }
    }

    pub fn open_req(&self, width: i32, height: i32, flags: IntPtr, name: &str) -> IntPtr {
        let name = c_string(name);
        unsafe { TVOpenReq(self.0, width, height, 0, 0, flags, name.as_ptr()) }
    }

    pub fn open_filter_req(
        &self,
        width: i32,
        height: i32,
        req_flags: IntPtr,
        menu_flags: IntPtr,
    ) -> IntPtr {
        unsafe {
            TVOpenFilterReqEx(
                self.0,
                width,
                height,
                None,
                std::ptr::null_mut(),
                req_flags,
                menu_flags,
            )
        }
    }

    pub fn close_req(&self, req: IntPtr) {
        unsafe { TVCloseReq(self.0, req) }
    }

    pub fn set_req_title(&self, req: IntPtr, title: &str) {
        let title = c_string(title);
        unsafe { TVSetReqTitle(self.0, req, title.as_ptr()) };
    }

    pub fn req_to_front(&self, req: IntPtr) {
        unsafe { TVReqToFront(self.0, req) };
    }

    pub fn req_info(&self, req: IntPtr) -> ReqInfo {
        let (mut x, mut y, mut w, mut h) = (0, 0, 0, 0);
        unsafe { TVInfoReq(self.0, req, &mut x, &mut y, &mut w, &mut h) };
        ReqInfo { x, y }
    }

    pub fn resize_req(&self, req: IntPtr, x: i32, y: i32, width: i32, height: i32) {
        unsafe { TVResizeReq(self.0, req, x, y, width, height) };
    }

    pub fn grab_ticks(&self, req: IntPtr) {
        unsafe { TVGrabTicks(self.0, req, AYON_PITICKS_FLAG_ON) };
    }

    #[allow(clippy::too_many_arguments)]
    pub fn add_button(
        &self,
        req: IntPtr,
        x: i32,
        y: i32,
        width: i32,
        id: i32,
        flags: IntPtr,
        label: &str,
    ) {
        let label = c_string(label);
        unsafe { TVAddButtonReq(self.0, req, x, y, width, 0, id, flags, label.as_ptr()) };
    }

    pub fn remove_button(&self, req: IntPtr, id: i32) {
        unsafe { TVRemoveButtonReq(self.0, req, id) };
    }

    pub fn set_button_info_text(&self, req: IntPtr, id: i32, text: &str) {
        let text = c_string(text);
        unsafe { TVSetButtonInfoText(self.0, req, id, text.as_ptr()) };
    }

    pub fn warning(&self, text: &str) {
        let text = c_string(text);
        unsafe { TVWarning(self.0, text.as_ptr()) }
    }

    pub fn execute(&self) {
        unsafe { TVExecute(self.0) };
    }

    /// Execute george script and return its raw output and success flag.
    pub fn send_cmd(&self, script: &CStr) -> (Vec<u8>, bool) {
        let mut output = vec![0u8; GEORGE_OUTPUT_SIZE];
        let success = unsafe {
            TVSendCmd(self.0, script.as_ptr(), output.as_mut_ptr() as *mut c_char)
        } != 0;
        // Keep the last byte as terminator in case TVPaint filled the buffer
        let length = output[..GEORGE_OUTPUT_SIZE - 1]
            .iter()
            .position(|byte| *byte == 0)
            .unwrap_or(GEORGE_OUTPUT_SIZE - 1);
        output.truncate(length);
        (output, success)
    }

    pub fn read_user_string(&self, section: &str, name: &str, default: &str) -> String {
        let section = c_string(section);
        let name = c_string(name);
        let default = c_string(default);
        let mut value = [0 as c_char; 256];
        unsafe {
            TVReadUserString(
                self.0,
                section.as_ptr(),
                name.as_ptr(),
                value.as_mut_ptr(),
                default.as_ptr(),
                (value.len() - 1) as c_int,
            );
            CStr::from_ptr(value.as_ptr()).to_string_lossy().into_owned()
        }
    }

    pub fn write_user_string(&self, section: &str, name: &str, value: &str) {
        let section = c_string(section);
        let name = c_string(name);
        let value = c_string(value);
        unsafe { TVWriteUserString(self.0, section.as_ptr(), name.as_ptr(), value.as_ptr()) };
    }
}

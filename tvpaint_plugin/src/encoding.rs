//! Conversion of george commands and their output.
//!
//! On Windows TVPaint works with text in the active ANSI code page, e.g.
//! UTF-8 bytes in a path make TVPaint show "Can't create file" dialog.

use std::ffi::CString;

#[cfg(windows)]
pub fn to_utf8(bytes: &[u8]) -> String {
    use windows_sys::Win32::Globalization::{MultiByteToWideChar, CP_ACP};

    if bytes.is_empty() {
        return String::new();
    }
    let Ok(length) = i32::try_from(bytes.len()) else {
        return String::from_utf8_lossy(bytes).into_owned();
    };
    unsafe {
        let size = MultiByteToWideChar(
            CP_ACP,
            0,
            bytes.as_ptr(),
            length,
            std::ptr::null_mut(),
            0,
        );
        if size <= 0 {
            return String::from_utf8_lossy(bytes).into_owned();
        }
        let mut wide = vec![0u16; size as usize];
        MultiByteToWideChar(CP_ACP, 0, bytes.as_ptr(), length, wide.as_mut_ptr(), size);
        String::from_utf16_lossy(&wide)
    }
}

#[cfg(not(windows))]
pub fn to_utf8(bytes: &[u8]) -> String {
    String::from_utf8_lossy(bytes).into_owned()
}

/// Convert command to bytes TVPaint understands.
///
/// Fails if the command contains NUL byte or, on Windows, characters that
/// are not available in the active code page. Passing them to TVPaint
/// would e.g. point to a different path.
#[cfg(windows)]
pub fn to_tvpaint(text: &str) -> Result<CString, String> {
    use windows_sys::Win32::Globalization::{
        WideCharToMultiByte, CP_ACP, WC_NO_BEST_FIT_CHARS,
    };

    if text.contains('\0') {
        return Err("George command contains NUL character".into());
    }
    if text.is_ascii() {
        return Ok(CString::new(text).unwrap_or_default());
    }
    let wide: Vec<u16> = text.encode_utf16().collect();
    let Ok(length) = i32::try_from(wide.len()) else {
        return Err("George command is too long".into());
    };
    unsafe {
        let mut used_default = 0;
        let size = WideCharToMultiByte(
            CP_ACP,
            WC_NO_BEST_FIT_CHARS,
            wide.as_ptr(),
            length,
            std::ptr::null_mut(),
            0,
            std::ptr::null(),
            &mut used_default,
        );
        if size <= 0 || used_default != 0 {
            return Err(format!(
                "George command contains characters which are not available in \
                 the system code page and TVPaint can't receive them: {text}"
            ));
        }
        let mut bytes = vec![0u8; size as usize];
        WideCharToMultiByte(
            CP_ACP,
            WC_NO_BEST_FIT_CHARS,
            wide.as_ptr(),
            length,
            bytes.as_mut_ptr(),
            size,
            std::ptr::null(),
            std::ptr::null_mut(),
        );
        Ok(CString::new(bytes).unwrap_or_default())
    }
}

#[cfg(not(windows))]
pub fn to_tvpaint(text: &str) -> Result<CString, String> {
    CString::new(text).map_err(|_| "George command contains NUL character".into())
}

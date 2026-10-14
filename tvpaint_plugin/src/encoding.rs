//! Conversion of george output to UTF-8.
//!
//! On Windows TVPaint returns george output in the active ANSI code page.

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

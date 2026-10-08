//! MatrixHunter 统一错误类型（对应原 infra/errors.py）。
//!
//! 所有错误序列化为 `{code, message}` 交给前端展示。

use serde::Serialize;

#[derive(Debug, Clone)]
pub enum MhError {
    ProcessList(String),
    Attach(String),
    MemoryRead { message: String, code: String },
    InvalidAddress(String),
    Enumeration(String),
    Window(String),
    Other(String),
}

impl MhError {
    pub fn code(&self) -> &'static str {
        match self {
            MhError::ProcessList(_) => "PROCESS_LIST_ERROR",
            MhError::Attach(_) => "ATTACH_ERROR",
            MhError::MemoryRead { code, .. } => {
                if code.is_empty() {
                    "MEMORY_READ_ERROR"
                } else {
                    // 借用返回要求静态；用固定串表达已知码
                    if code == "PROCESS_EXITED" {
                        "PROCESS_EXITED"
                    } else {
                        "MEMORY_READ_ERROR"
                    }
                }
            }
            MhError::InvalidAddress(_) => "INVALID_ADDRESS",
            MhError::Enumeration(_) => "ENUMERATION_ERROR",
            MhError::Window(_) => "WINDOW_ERROR",
            MhError::Other(_) => "ERROR",
        }
    }

    pub fn message(&self) -> String {
        match self {
            MhError::ProcessList(m)
            | MhError::Attach(m)
            | MhError::InvalidAddress(m)
            | MhError::Enumeration(m)
            | MhError::Window(m)
            | MhError::Other(m) => m.clone(),
            MhError::MemoryRead { message, .. } => message.clone(),
        }
    }
}

impl std::fmt::Display for MhError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.message())
    }
}

impl std::error::Error for MhError {}

/// 前端可见的错误负载。
#[derive(Debug, Clone, Serialize)]
pub struct ErrorPayload {
    pub code: String,
    pub message: String,
}

impl From<MhError> for ErrorPayload {
    fn from(e: MhError) -> Self {
        ErrorPayload {
            code: e.code().to_string(),
            message: e.message(),
        }
    }
}

impl Serialize for MhError {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        ErrorPayload::from(self.clone()).serialize(serializer)
    }
}

pub type MhResult<T> = Result<T, MhError>;

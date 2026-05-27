#[cfg(not(debug_assertions))]
use std::sync::Mutex;

#[cfg(not(debug_assertions))]
use tauri::Manager;
#[cfg(not(debug_assertions))]
use tauri_plugin_shell::{process::CommandChild, process::CommandEvent, ShellExt};

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[cfg(not(debug_assertions))]
struct ApiSidecar(Mutex<Option<CommandChild>>);

#[cfg(not(debug_assertions))]
impl Drop for ApiSidecar {
    fn drop(&mut self) {
        if let Ok(mut child) = self.0.lock() {
            if let Some(child) = child.take() {
                let _ = child.kill();
            }
        }
    }
}

#[cfg(not(debug_assertions))]
fn spawn_api_sidecar(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let (mut rx, child) = app
        .shell()
        .sidecar("binaries/helix-api")?
        .env("UCARD_API_HOST", "127.0.0.1")
        .env("UCARD_API_PORT", "8765")
        .env("UCARD_API_RELOAD", "false")
        .spawn()?;

    app.manage(ApiSidecar(Mutex::new(Some(child))));

    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    println!("[helix-api] {}", String::from_utf8_lossy(&line).trim_end());
                }
                CommandEvent::Stderr(line) => {
                    eprintln!("[helix-api] {}", String::from_utf8_lossy(&line).trim_end());
                }
                _ => {}
            }
        }
    });

    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .setup(|_app| {
            #[cfg(not(debug_assertions))]
            spawn_api_sidecar(_app)?;

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![greet]);

    builder
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

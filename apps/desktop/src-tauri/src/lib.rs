#[cfg(not(debug_assertions))]
use std::sync::Mutex;

#[cfg(not(debug_assertions))]
use std::{
    fs::OpenOptions,
    io::{Read, Write},
    net::{TcpListener, TcpStream},
    time::Duration,
};
use tauri::Manager;
use tauri::WindowEvent;
#[cfg(not(debug_assertions))]
use tauri_plugin_shell::{process::CommandChild, process::CommandEvent, ShellExt};

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[cfg(not(debug_assertions))]
struct ApiSidecar(Mutex<Option<CommandChild>>);

#[cfg(not(debug_assertions))]
struct ApiEndpoint(String);

#[cfg(not(debug_assertions))]
impl Drop for ApiSidecar {
    fn drop(&mut self) {
        self.kill();
    }
}

#[cfg(not(debug_assertions))]
impl ApiSidecar {
    fn kill(&self) {
        if let Ok(mut child) = self.0.lock() {
            if let Some(child) = child.take() {
                let _ = child.kill();
            }
        }
    }
}

#[cfg(not(debug_assertions))]
fn find_available_port() -> std::io::Result<u16> {
    TcpListener::bind(("127.0.0.1", 0)).and_then(|listener| {
        let port = listener.local_addr()?.port();
        drop(listener);
        Ok(port)
    })
}

#[cfg(not(debug_assertions))]
fn spawn_api_sidecar(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let data_dir = app.path().app_data_dir()?;
    std::fs::create_dir_all(&data_dir)?;
    let port = find_available_port()?;
    let endpoint = format!("http://127.0.0.1:{port}");

    let (mut rx, child) = app
        .shell()
        .sidecar("helix-api")?
        .env("UCARD_API_HOST", "127.0.0.1")
        .env("UCARD_API_PORT", port.to_string())
        .env("UCARD_API_RELOAD", "false")
        .env("UCARD_DATA_DIR", data_dir.as_os_str())
        .spawn()?;

    log_sidecar_message(&format!(
        "started helix-api pid={} endpoint={endpoint}",
        child.pid()
    ));
    app.manage(ApiSidecar(Mutex::new(Some(child))));
    app.manage(ApiEndpoint(endpoint));

    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    println!("[helix-api] {}", String::from_utf8_lossy(&line).trim_end());
                }
                CommandEvent::Stderr(line) => {
                    let message =
                        format!("[helix-api] {}", String::from_utf8_lossy(&line).trim_end());
                    eprintln!("{message}");
                    log_sidecar_message(&message);
                }
                CommandEvent::Error(error) => {
                    log_sidecar_message(&format!("sidecar stream error: {error}"))
                }
                CommandEvent::Terminated(payload) => log_sidecar_message(&format!(
                    "helix-api terminated code={:?} signal={:?}",
                    payload.code, payload.signal
                )),
                _ => {}
            }
        }
    });

    Ok(())
}

#[cfg(not(debug_assertions))]
#[tauri::command]
fn api_endpoint(endpoint: tauri::State<ApiEndpoint>) -> String {
    endpoint.0.clone()
}

#[cfg(debug_assertions)]
#[tauri::command]
fn api_endpoint() -> String {
    "http://127.0.0.1:8765".to_string()
}

#[cfg(not(debug_assertions))]
fn log_sidecar_message(message: &str) {
    if let Ok(mut file) = OpenOptions::new()
        .create(true)
        .append(true)
        .open("/tmp/helix-sidecar.log")
    {
        let _ = writeln!(file, "{message}");
    }
}

#[cfg(not(debug_assertions))]
fn send_backend_post(endpoint: &str, path: &str, read_timeout: Duration) -> std::io::Result<()> {
    let host = endpoint.strip_prefix("http://").unwrap_or(endpoint);
    let address = host
        .strip_prefix("http://")
        .parse()
        .expect("valid backend address");
    let mut stream = TcpStream::connect_timeout(
        &address,
        Duration::from_secs(2),
    )?;
    stream.set_read_timeout(Some(read_timeout))?;
    stream.set_write_timeout(Some(Duration::from_secs(2)))?;
    let request = format!(
        "POST {path} HTTP/1.1\r\nHost: {host}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    );
    stream.write_all(request.as_bytes())?;

    let mut response = Vec::new();
    let _ = stream.read_to_end(&mut response);
    Ok(())
}

#[cfg(not(debug_assertions))]
fn stop_backend<R: tauri::Runtime>(app_handle: &tauri::AppHandle<R>) {
    let Some(endpoint) = app_handle.try_state::<ApiEndpoint>() else {
        return;
    };
    let _ = send_backend_post(&endpoint.0, "/api/tasks/runs/active/stop", Duration::from_secs(15));
    let _ = send_backend_post(&endpoint.0, "/shutdown", Duration::from_secs(2));
    std::thread::sleep(Duration::from_millis(500));
}

#[cfg(not(debug_assertions))]
fn kill_api_sidecar<R: tauri::Runtime>(app_handle: &tauri::AppHandle<R>) {
    if let Some(sidecar) = app_handle.try_state::<ApiSidecar>() {
        sidecar.kill();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|_app| {
            #[cfg(not(debug_assertions))]
            if let Err(error) = spawn_api_sidecar(_app) {
                let message = format!("failed to start helix-api sidecar: {error}");
                eprintln!("{message}");
                log_sidecar_message(&message);
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                window.app_handle().exit(0);
            }
        })
        .invoke_handler(tauri::generate_handler![greet, api_endpoint]);

    let app = builder
        .build(tauri::generate_context!())
        .expect("error while running tauri application");

    app.run(|_app_handle, event| match event {
        tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit => {
            #[cfg(not(debug_assertions))]
            {
                stop_backend(_app_handle);
                kill_api_sidecar(_app_handle);
            }
        }
        _ => {}
    });
}

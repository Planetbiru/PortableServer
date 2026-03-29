<?php

require_once __DIR__ . "/fn.php";

echo COLOR_BLUE . "=== MagicAppBuilder Portable Stopper ===\n" . COLOR_NC;

$processesToStop = [
    "httpd.exe"        => "Apache",
    "mysqld.exe"       => "MariaDB",
    "redis-server.exe" => "Redis",
];

// Stop Redis service (redis-server.exe)
echo "Stopping Redis (redis-server.exe)...\n";
stopProcessByName("redis-server.exe");
foreach ($processesToStop as $processName => $serviceName) {
    echo "Stopping $serviceName ($processName)...\n";
    
    // Use shell_exec for a more robust, fire-and-forget command execution on Windows.
    // The `2>nul` part redirects any errors from taskkill itself, preventing them
    // from interfering with the PHP script's output pipes. This is more stable
    // than managing pipes with proc_open for this specific task.
    // The output of taskkill is captured but ignored.
    @shell_exec("taskkill /F /IM \"$processName\" 2>nul");
}

// Stop Apache HTTP server (httpd.exe)
echo "Stopping Apache (httpd.exe)...\n";
stopProcessByName("httpd.exe");

echo COLOR_GREEN . "✅ All services stopped.\n" . COLOR_NC;

<?php

require_once __DIR__ . "/fn.php";
require_once __DIR__ . "/stop.php";

$phpPath     = __DIR__ . '/php';
$phpExtPath  = __DIR__ . '/php/ext';
$currentPath = getenv('PATH');

$paths = explode(PATH_SEPARATOR, $currentPath);

// Tambahkan hanya jika belum ada
if (!in_array($phpPath, $paths)) {
    $paths[] = $phpPath;
}
if (!in_array($phpExtPath, $paths)) {
    $paths[] = $phpExtPath;
}

// Gabungkan kembali dan set PATH
putenv('PATH=' . implode(PATH_SEPARATOR, $paths));


$newPathToAdd = __DIR__ . "/php/bin";
$newPathToAdd = __DIR__ . "/mysql/bin";

// Ensure necessary directories
ensureDirectory(__DIR__ . "/www");
ensureDirectory(__DIR__ . "/tmp");
ensureDirectory(__DIR__ . "/data");
ensureDirectory(__DIR__ . "/data/mysql");
ensureDirectory(__DIR__ . "/data/redis");
ensureDirectory(__DIR__ . "/logs");
ensureDirectory(__DIR__ . "/sessions");
ensureDirectory(__DIR__ . "/apache/logs");


// Replace config templates
replaceAndWrite(__DIR__ . "/config/httpd-template.conf", __DIR__ . "/config/httpd.conf");
replaceAndWrite(__DIR__ . "/config/php-template.ini", __DIR__ . "/php/php.ini");
replaceAndWrite(__DIR__ . "/config/my-template.ini", __DIR__ . "/config/my.ini");
replaceAndWrite(__DIR__ . "/config/redis.windows-template.conf", __DIR__ . "/redis/redis.windows.conf");
replaceAndWrite(__DIR__ . "/config/redis.windows-service-template.conf", __DIR__ . "/redis/redis.windows-service.conf");


echo "=== MagicAppBuilder Portable Installer ===\n";

// Set path
$apacheBin = __DIR__ . "/apache/bin/httpd.exe";
$mysqlBin = __DIR__ . "/mysql/bin/mysqld.exe";
$redisBin = __DIR__ . "/redis/redis-server.exe";

// Cek dependensi
if (!file_exists($apacheBin)) {
    echo "[ERROR] Apache not found!\n";
    exit(1);
}

if (!file_exists($mysqlBin)) {
    echo "[ERROR] MySQL/MariaDB not found!\n";
    exit(1);
}

// Cek port
function isPortInUse($port) {
    $conn = @fsockopen("127.0.0.1", $port);
    if ($conn) {
        fclose($conn);
        return true;
    }
    return false;
}

if (isPortInUse(80)) {
    echo "[WARNING] Port 80 already in use.\n";
}

if (isPortInUse(3306)) {
    echo "[WARNING] Port 3306 already in use.\n";
}



// Jalankan MySQL
echo "Starting MySQL...\n";
$cmd1 = "start /B \"\" \"" . $mysqlBin . "\" --defaults-file=\"" . __DIR__ . "/config/my.ini"; // NOSONAR
pclose(popen($cmd1, "r"));

// Jalankan Redis
echo "Starting Redis...\n";
$cmd2 = "start /B \"\" \"" . $redisBin . "\""; // NOSONAR
pclose(popen($cmd2, "r"));

// Jalankan Apache
echo "Starting Apache...\n";
$cmd3 = "start /B \"\" \"" . $apacheBin . "\" -f \"" . __DIR__ . "/config/httpd.conf\""; // NOSONAR
pclose(popen($cmd3, "r"));

echo "DONE. Access your app at http://localhost/MagicAppBuilder/\n";
$cmd4 = "start http://localhost/MagicAppBuilder/"; // NOSONAR
pclose(popen($cmd4, "r"));
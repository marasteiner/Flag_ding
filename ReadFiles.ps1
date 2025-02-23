# Definiere die Dateiendungen, die verarbeitet werden sollen
$extensions = ".py", ".html", ".css"

# Hole alle Dateien im aktuellen Verzeichnis und in allen Unterordnern, die den gewünschten Endungen entsprechen
$files = Get-ChildItem -Path . -File -Recurse | Where-Object { $extensions -contains $_.Extension }

# Verarbeite jede Datei
foreach ($file in $files) {
    try {
        # Lese den Inhalt der Datei
        $content = Get-Content -Path $file.FullName -ErrorAction Stop
        # Gib den Dateinamen (inklusive Pfad) und dessen Inhalt aus
        Write-Output "----- Start der Datei: $($file.FullName) -----"
        Write-Output $content
        Write-Output "----- Ende der Datei: $($file.FullName) -----`n"
    }
    catch {
        # Gib eine Fehlermeldung aus, falls die Datei nicht gelesen werden kann
        Write-Output "Fehler beim Lesen der Datei: $($file.FullName). Fehler: $_"
    }
}

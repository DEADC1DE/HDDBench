#!/bin/bash
# filepath: /home/HDDBench/nvme_optimizer.sh
# Purpose: Alles-in-Einem Skript zum Optimieren und Testen des NVMe-Laufwerks
# Erstellt am: $(date "+%Y-%m-%d")
# Version: 2.0

set -e

# Farbcodes für bessere Lesbarkeit
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
RED='\033[1;31m'
BLUE='\033[1;34m'
CYAN='\033[1;36m'
NC='\033[0m' # No Color

# Standardwerte
DEVICE="/dev/nvme0n1p5"
MOUNTPOINT="/mnt"
FS_TYPE="xfs"
MOUNT_OPTIONS="rw,noatime,allocsize=1m,discard"
RESULTS_DIR="/home/HDDBench/benchmark_results"
CSV_FILE="/home/HDDBench/all_fs_results.csv"

# Stellen Sie sicher, dass das Ergebnisverzeichnis existiert
mkdir -p "$RESULTS_DIR"

# Als Root prüfen
if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}Dieses Skript muss als Root ausgeführt werden${NC}"
    exit 1
fi

# Funktion: Aktuelle Konfiguration prüfen
check_current_config() {
    echo -e "${BLUE}=== Aktuelle Konfiguration prüfen ===${NC}"
    
    if mount | grep -q "${MOUNTPOINT}"; then
        current_fs=$(mount | grep ${MOUNTPOINT} | awk '{print $5}')
        current_options=$(mount | grep ${MOUNTPOINT} | awk '{$1=$2=$3=$4=$5=""; print $0}' | sed 's/^[ \t]*//' | tr -d '()')
        
        echo -e "Aktuelles Dateisystem: ${GREEN}${current_fs}${NC}"
        echo -e "Aktuelle Mount-Optionen: ${GREEN}${current_options}${NC}"
        
        # Prüfen, ob bereits optimal konfiguriert
        if [[ "${current_fs}" == "${FS_TYPE}" && "${current_options}" =~ "allocsize=1024k" && "${current_options}" =~ "noatime" && "${current_options}" =~ "discard" ]]; then
            echo -e "${GREEN}Das Laufwerk ist bereits optimal konfiguriert!${NC}"
            is_optimal=true
        else
            echo -e "${YELLOW}Das Laufwerk könnte optimiert werden.${NC}"
            echo -e "Empfohlenes Dateisystem: ${GREEN}${FS_TYPE}${NC}"
            echo -e "Empfohlene Mount-Optionen: ${GREEN}${MOUNT_OPTIONS}${NC}"
            is_optimal=false
        fi
    else
        echo -e "${RED}Das Laufwerk ${DEVICE} ist nicht unter ${MOUNTPOINT} gemountet${NC}"
        is_optimal=false
    fi
}

# Funktion: Laufwerk optimieren
optimize_drive() {
    echo -e "${BLUE}=== Laufwerk optimieren ===${NC}"
    
    # Prüfen, ob bereits gemountet
    if mount | grep -q "${MOUNTPOINT}"; then
        echo -e "${YELLOW}Unmounting ${MOUNTPOINT}...${NC}"
        umount ${MOUNTPOINT}
    fi
    
    # Dateisystem formatieren
    echo -e "${YELLOW}Formatiere ${DEVICE} als ${FS_TYPE}...${NC}"
    case "${FS_TYPE}" in
        "xfs")
            mkfs.xfs -f ${DEVICE}
            ;;
        "ext4")
            mkfs.ext4 -F ${DEVICE}
            ;;
        "btrfs")
            mkfs.btrfs -f ${DEVICE}
            ;;
        "f2fs")
            mkfs.f2fs -f ${DEVICE}
            ;;
        *)
            echo -e "${RED}Nicht unterstütztes Dateisystem: ${FS_TYPE}${NC}"
            exit 1
            ;;
    esac
    
    # Verzeichnisstruktur erstellen
    mkdir -p ${MOUNTPOINT}
    
    # Mit optimierten Optionen mounten
    echo -e "${YELLOW}Mounten mit Optionen: ${MOUNT_OPTIONS}${NC}"
    mount -t ${FS_TYPE} -o ${MOUNT_OPTIONS} ${DEVICE} ${MOUNTPOINT}
    
    # fstab-Eintrag aktualisieren
    if grep -q "${MOUNTPOINT}" /etc/fstab; then
        echo -e "${YELLOW}Aktualisiere bestehenden fstab-Eintrag...${NC}"
        # Bestehenden Eintrag sichern
        cp /etc/fstab /etc/fstab.backup.$(date +%Y%m%d%H%M%S)
        # Eintrag ersetzen
        sed -i "s|^.*${MOUNTPOINT}.*\$|${DEVICE}  ${MOUNTPOINT}  ${FS_TYPE}  ${MOUNT_OPTIONS}  0 2|" /etc/fstab
    else
        echo -e "${YELLOW}Füge neuen fstab-Eintrag hinzu...${NC}"
        echo "${DEVICE}  ${MOUNTPOINT}  ${FS_TYPE}  ${MOUNT_OPTIONS}  0 2" >> /etc/fstab
    fi
    
    # Systemd neu laden
    systemctl daemon-reload
    
    echo -e "${GREEN}Laufwerk erfolgreich optimiert!${NC}"
}

# Funktion: Performance testen
test_performance() {
    echo -e "${BLUE}=== Performance testen ===${NC}"
    
    # Testverzeichnis erstellen
    mkdir -p ${MOUNTPOINT}/speedtest
    
    # Cache leeren
    echo 3 > /proc/sys/vm/drop_caches
    
    # Direkter Schreibtest (1GB)
    echo -e "${YELLOW}Direkter Schreibtest (1GB)...${NC}"
    DIRECT_WRITE=$(dd if=/dev/zero of=${MOUNTPOINT}/speedtest/testfile_direct bs=1M count=1000 oflag=direct 2>&1 | grep -o ".*MB/s" | sed 's/MB\/s//')
    
    # Normaler Schreibtest (1GB)
    echo 3 > /proc/sys/vm/drop_caches
    echo -e "${YELLOW}Normaler Schreibtest (1GB)...${NC}"
    BUFFERED_WRITE=$(dd if=/dev/zero of=${MOUNTPOINT}/speedtest/testfile_buffered bs=1M count=1000 2>&1 | grep -o ".*MB/s" | sed 's/MB\/s//')
    
    # Lesetest (1GB)
    echo 3 > /proc/sys/vm/drop_caches
    echo -e "${YELLOW}Lesetest (1GB)...${NC}"
    READ_SPEED=$(dd if=${MOUNTPOINT}/speedtest/testfile_buffered of=/dev/null bs=1M 2>&1 | grep -o ".*MB/s" | sed 's/MB\/s//')
    
    # Ergebnisse anzeigen
    echo -e "\n${CYAN}=== Testergebnisse ====${NC}"
    echo -e "Direkter Schreibtest: ${GREEN}${DIRECT_WRITE} MB/s${NC}"
    echo -e "Normaler Schreibtest: ${GREEN}${BUFFERED_WRITE} MB/s${NC}"
    echo -e "Lesetest:            ${GREEN}${READ_SPEED} MB/s${NC}"
    
    # Aufräumen
    rm -f ${MOUNTPOINT}/speedtest/testfile_*
    rmdir ${MOUNTPOINT}/speedtest
    
    echo -e "${GREEN}Performance-Tests abgeschlossen!${NC}"
}

# Funktion: Benchmark für ein einzelnes Dateisystem
benchmark_single_fs() {
    local fs_type="$1"
    local mount_options="$2"
    local test_name="${fs_type}_${mount_options//[,=]/_}"
    local timestamp=$(date +%Y%m%d%H%M%S)
    local result_file="${RESULTS_DIR}/result_${test_name}_${timestamp}.txt"
    
    echo -e "${BLUE}=== Benchmark für $fs_type mit Optionen: $mount_options ===${NC}"
    
    # Unmount, falls gemountet
    if mount | grep -q "${MOUNTPOINT}"; then
        echo -e "${YELLOW}Unmounting ${MOUNTPOINT}...${NC}"
        umount ${MOUNTPOINT}
    fi
    
    # Dateisystem formatieren
    echo -e "${YELLOW}Formatiere ${DEVICE} mit ${fs_type}...${NC}"
    case "$fs_type" in
        ext4)
            mkfs.ext4 -F "$DEVICE"
            ;;
        xfs)
            mkfs.xfs -f "$DEVICE"
            ;;
        btrfs)
            mkfs.btrfs -f "$DEVICE"
            ;;
        f2fs)
            if command -v mkfs.f2fs &> /dev/null; then
                mkfs.f2fs -f "$DEVICE"
            else
                echo -e "${RED}mkfs.f2fs nicht gefunden. Installiere mit: apt-get install f2fs-tools${NC}"
                return 1
            fi
            ;;
        *)
            echo -e "${RED}Unbekanntes Dateisystem: $fs_type${NC}"
            return 1
            ;;
    esac
    
    # Mounten mit den angegebenen Optionen
    echo -e "${YELLOW}Mounte ${DEVICE} auf ${MOUNTPOINT} mit Optionen: ${mount_options}${NC}"
    mkdir -p ${MOUNTPOINT}
    mount -t "$fs_type" -o "$mount_options" "$DEVICE" "$MOUNTPOINT"
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}Mount fehlgeschlagen. Überprüfe Optionen und Berechtigungen.${NC}"
        return 1
    fi
    
    # Benchmark durchführen
    echo -e "${YELLOW}Führe Benchmark durch...${NC}"
    
    # Cache leeren
    sync
    echo 3 > /proc/sys/vm/drop_caches
    
    # Schreibtest mit dd (direktem I/O)
    echo "Schreibtest mit direktem I/O (1GB)..."
    DIRECT_WRITE=$(dd if=/dev/zero of="${MOUNTPOINT}/testfile_direct" bs=1M count=1000 oflag=direct conv=fsync 2>&1 | grep "bytes" | grep -o "[0-9.]* MB/s" | sed 's/MB\/s//')
    echo "Direkt-Schreiben: ${DIRECT_WRITE} MB/s" | tee -a "$result_file"
    
    # Cache leeren
    sync
    echo 3 > /proc/sys/vm/drop_caches
    
    # Schreibtest mit gepuffertem I/O
    echo "Schreibtest mit gepuffertem I/O (1GB)..."
    BUFFERED_WRITE=$(dd if=/dev/zero of="${MOUNTPOINT}/testfile_buffered" bs=1M count=1000 conv=fsync 2>&1 | grep "bytes" | grep -o "[0-9.]* MB/s" | sed 's/MB\/s//')
    echo "Gepuffertes Schreiben: ${BUFFERED_WRITE} MB/s" | tee -a "$result_file"
    
    # Cache leeren
    sync
    echo 3 > /proc/sys/vm/drop_caches
    
    # Lesetest
    echo "Lesetest (1GB)..."
    READ_SPEED=$(dd if="${MOUNTPOINT}/testfile_direct" of=/dev/null bs=1M 2>&1 | grep "bytes" | grep -o "[0-9.]* MB/s" | sed 's/MB\/s//')
    echo "Lesen: ${READ_SPEED} MB/s" | tee -a "$result_file"
    
    # Aufräumen
    rm -f "${MOUNTPOINT}/testfile_direct" "${MOUNTPOINT}/testfile_buffered"
    
    # Prüfen, ob die Werte numerisch sind
    if [[ ! "$DIRECT_WRITE" =~ ^[0-9]+(\.[0-9]+)?$ ]] || [[ ! "$BUFFERED_WRITE" =~ ^[0-9]+(\.[0-9]+)?$ ]] || [[ ! "$READ_SPEED" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
        echo -e "${RED}Fehler bei der Extraktion von Benchmark-Ergebnissen.${NC}"
        # Fallback-Werte
        DIRECT_WRITE="0"
        BUFFERED_WRITE="0"
        READ_SPEED="0"
    fi
    
    # In CSV speichern, wenn sie existiert oder erstellen
    if [ ! -f "$CSV_FILE" ]; then
        echo "filesystem,mount_options,direct_write_speed,buffered_write_speed,read_speed" > "$CSV_FILE"
    fi
    echo "$fs_type,$mount_options,$DIRECT_WRITE,$BUFFERED_WRITE,$READ_SPEED" >> "$CSV_FILE"
    
    # Ergebnisse anzeigen
    echo -e "\n${CYAN}=== Testergebnisse ====${NC}"
    echo -e "Dateisystem:         ${GREEN}${fs_type}${NC}"
    echo -e "Mount-Optionen:      ${GREEN}${mount_options}${NC}"
    echo -e "Direkt-Schreiben:    ${GREEN}${DIRECT_WRITE} MB/s${NC}"
    echo -e "Gepuffert-Schreiben: ${GREEN}${BUFFERED_WRITE} MB/s${NC}"
    echo -e "Lesen:               ${GREEN}${READ_SPEED} MB/s${NC}"
    
    echo -e "\n${GREEN}Benchmark abgeschlossen. Ergebnisse in ${result_file} und ${CSV_FILE} gespeichert.${NC}"
    
    # Unmount
    umount "$MOUNTPOINT"
    
    return 0
}

# Funktion: Alle Dateisysteme und Optionen testen
test_all_fs() {
    echo -e "${BLUE}=== Benchmark für alle Dateisysteme und Optionen ===${NC}"
    
    # CSV-Header erstellen
    echo "filesystem,mount_options,direct_write_speed,buffered_write_speed,read_speed" > "$CSV_FILE"
    
    # ext4 Tests
    benchmark_single_fs "ext4" "rw,noatime"
    benchmark_single_fs "ext4" "rw,noatime,discard"
    benchmark_single_fs "ext4" "rw,noatime,data=writeback"
    benchmark_single_fs "ext4" "rw,noatime,data=ordered"
    
    # XFS Tests (unsere empfohlene Konfiguration)
    benchmark_single_fs "xfs" "rw,noatime"
    benchmark_single_fs "xfs" "rw,noatime,discard"
    benchmark_single_fs "xfs" "rw,noatime,allocsize=1m"
    benchmark_single_fs "xfs" "rw,noatime,allocsize=1m,discard"
    
    # Btrfs Tests
    benchmark_single_fs "btrfs" "rw,noatime"
    benchmark_single_fs "btrfs" "rw,noatime,discard"
    benchmark_single_fs "btrfs" "rw,noatime,compress=zstd"
    benchmark_single_fs "btrfs" "rw,noatime,discard,compress=zstd"
    
    # F2FS Tests, falls verfügbar
    if command -v mkfs.f2fs &> /dev/null; then
        benchmark_single_fs "f2fs" "rw,noatime"
        benchmark_single_fs "f2fs" "rw,noatime,discard"
    fi
    
    echo -e "${GREEN}Alle Tests abgeschlossen. Ergebnisse in ${CSV_FILE} gespeichert.${NC}"
    analyze_results
}

# Funktion: Ergebnisse analysieren
analyze_results() {
    echo -e "${BLUE}=== Benchmark-Ergebnisse analysieren ===${NC}"
    
    if [ ! -f "$CSV_FILE" ]; then
        echo -e "${RED}Keine Ergebnisdatei gefunden (${CSV_FILE}).${NC}"
        return 1
    fi
    
    # Header überspringen
    HEADER=$(head -n 1 "$CSV_FILE")
    
    # Sortieren nach direkter Schreibgeschwindigkeit (wichtigster Faktor für FTP)
    echo -e "${CYAN}Top 5 Konfigurationen für direktes Schreiben:${NC}"
    sort -t, -k3 -nr <(tail -n +2 "$CSV_FILE") | head -n 5 | 
    while IFS=, read fs opts direct_write buffered_write read_speed; do
        echo -e "${GREEN}${fs}${NC} mit ${YELLOW}${opts}${NC}: ${GREEN}${direct_write} MB/s${NC}"
    done
    
    echo ""
    
    # Sortieren nach gepuffertem Schreiben
    echo -e "${CYAN}Top 5 Konfigurationen für gepuffertes Schreiben:${NC}"
    sort -t, -k4 -nr <(tail -n +2 "$CSV_FILE") | head -n 5 | 
    while IFS=, read fs opts direct_write buffered_write read_speed; do
        echo -e "${GREEN}${fs}${NC} mit ${YELLOW}${opts}${NC}: ${GREEN}${buffered_write} MB/s${NC}"
    done
    
    echo ""
    
    # Sortieren nach Lesegeschwindigkeit
    echo -e "${CYAN}Top 5 Konfigurationen für Lesen:${NC}"
    sort -t, -k5 -nr <(tail -n +2 "$CSV_FILE") | head -n 5 | 
    while IFS=, read fs opts direct_write buffered_write read_speed; do
        echo -e "${GREEN}${fs}${NC} mit ${YELLOW}${opts}${NC}: ${GREEN}${read_speed} MB/s${NC}"
    done
    
    echo ""
    
    # Beste Gesamtkonfiguration (gewichteter Durchschnitt: 50% direkt, 30% gepuffert, 20% lesen)
    echo -e "${CYAN}Top 5 Konfigurationen nach gewichtetem Durchschnitt:${NC}"
    echo -e "${YELLOW}(50% direktes Schreiben, 30% gepuffertes Schreiben, 20% Lesen)${NC}"
    
    # Temporäre Datei mit gewichtetem Durchschnitt
    TMP_FILE=$(mktemp)
    tail -n +2 "$CSV_FILE" | 
    while IFS=, read fs opts direct_write buffered_write read_speed; do
        # Gewichteten Durchschnitt berechnen
        avg=$(echo "scale=2; ($direct_write * 0.5) + ($buffered_write * 0.3) + ($read_speed * 0.2)" | bc)
        echo "$fs,$opts,$direct_write,$buffered_write,$read_speed,$avg"
    done > "$TMP_FILE"
    
    # Nach gewichtetem Durchschnitt sortieren und Top 5 anzeigen
    sort -t, -k6 -nr "$TMP_FILE" | head -n 5 | 
    while IFS=, read fs opts direct_write buffered_write read_speed avg; do
        echo -e "${GREEN}${fs}${NC} mit ${YELLOW}${opts}${NC}: ${GREEN}${avg} (gewichtet)${NC}"
        echo -e "  Direkt: ${direct_write} MB/s, Gepuffert: ${buffered_write} MB/s, Lesen: ${read_speed} MB/s"
    done
    
    # Temporäre Datei löschen
    rm -f "$TMP_FILE"
    
    echo ""
    echo -e "${GREEN}Analyse abgeschlossen.${NC}"
    echo -e "Die vollständigen Ergebnisse findest du in: ${YELLOW}${CSV_FILE}${NC}"
}

# Hauptmenü
show_menu() {
    clear
    echo -e "${BLUE}=======================================${NC}"
    echo -e "${BLUE}===    NVMe-Laufwerk Optimierer    ===${NC}"
    echo -e "${BLUE}=======================================${NC}"
    echo -e "1) ${GREEN}Aktuelle Konfiguration prüfen${NC}"
    echo -e "2) ${YELLOW}Laufwerk optimieren (XFS mit optimalen Einstellungen)${NC}"
    echo -e "3) ${YELLOW}Performance schnell testen${NC}"
    echo -e "4) ${CYAN}Einzelnes Dateisystem testen${NC}"
    echo -e "5) ${CYAN}Alle Dateisysteme und Optionen umfassend testen${NC}"
    echo -e "6) ${CYAN}Testergebnisse analysieren${NC}"
    echo -e "7) ${RED}Beenden${NC}"
    echo ""
    echo -n "Bitte wähle eine Option (1-7): "
    read choice
    
    case $choice in
        1)
            check_current_config
            ;;
        2)
            echo -e "${RED}WARNUNG: Dies wird alle Daten auf ${DEVICE} löschen!${NC}"
            echo -n "Möchtest du fortfahren? (j/N): "
            read confirm
            if [[ "$confirm" == "j" || "$confirm" == "J" ]]; then
                optimize_drive
            else
                echo -e "${YELLOW}Optimierung abgebrochen.${NC}"
            fi
            ;;
        3)
            test_performance
            ;;
        4)
            echo -e "${BLUE}=== Einzelnes Dateisystem testen ===${NC}"
            echo "Verfügbare Dateisysteme: ext4, xfs, btrfs, f2fs"
            echo -n "Dateisystem wählen: "
            read test_fs
            
            echo "Beispiele für Mount-Optionen:"
            echo " - ext4: rw,noatime,discard,data=writeback"
            echo " - xfs: rw,noatime,allocsize=1m,discard"
            echo " - btrfs: rw,noatime,discard,compress=zstd"
            echo " - f2fs: rw,noatime,discard"
            echo -n "Mount-Optionen eingeben: "
            read test_options
            
            echo -e "${RED}WARNUNG: Dies wird alle Daten auf ${DEVICE} löschen!${NC}"
            echo -n "Möchtest du fortfahren? (j/N): "
            read confirm
            if [[ "$confirm" == "j" || "$confirm" == "J" ]]; then
                benchmark_single_fs "$test_fs" "$test_options"
            else
                echo -e "${YELLOW}Test abgebrochen.${NC}"
            fi
            ;;
        5)
            echo -e "${RED}WARNUNG: Diese Option führt umfangreiche Tests durch und formatiert${NC}"
            echo -e "${RED}das Laufwerk mehrfach. Alle Daten auf ${DEVICE} werden gelöscht!${NC}"
            echo -e "${YELLOW}Diese Tests dauern sehr lange (ca. 30+ Minuten)${NC}"
            echo -n "Möchtest du fortfahren? (j/N): "
            read confirm
            if [[ "$confirm" == "j" || "$confirm" == "J" ]]; then
                test_all_fs
            else
                echo -e "${YELLOW}Tests abgebrochen.${NC}"
            fi
            ;;
        6)
            analyze_results
            ;;
        7)
            echo -e "${BLUE}Auf Wiedersehen!${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}Ungültige Option.${NC}"
            ;;
    esac
    
    echo ""
    echo -n "Drücke Enter, um zum Hauptmenü zurückzukehren..."
    read dummy
    show_menu
}

# Hilfefunktion
show_help() {
    echo -e "${BLUE}NVMe Optimizer - Hilfe${NC}"
    echo "Ein Skript zur Optimierung von NVMe-Laufwerken"
    echo
    echo "Verwendung: $0 [Option]"
    echo
    echo "Optionen:"
    echo "  -h, --help         Diese Hilfe anzeigen"
    echo "  -c, --check        Aktuelle Konfiguration prüfen"
    echo "  -o, --optimize     Laufwerk mit optimalen Einstellungen formatieren"
    echo "  -t, --test         Schnelltest der aktuellen Konfiguration durchführen"
    echo "  -a, --all-tests    Alle Dateisysteme und Optionen testen"
    echo "  -s, --show         Ergebnisse der Tests anzeigen"
    echo "  -m, --menu         Interaktives Menü anzeigen (Standard)"
    echo
    echo "Beispiel: $0 --check"
    echo
}

# Kommandozeilenparameter verarbeiten
if [ $# -gt 0 ]; then
    case "$1" in
        -h|--help)
            show_help
            exit 0
            ;;
        -c|--check)
            check_current_config
            exit 0
            ;;
        -o|--optimize)
            echo -e "${RED}WARNUNG: Dies wird alle Daten auf ${DEVICE} löschen!${NC}"
            echo -n "Möchtest du fortfahren? (j/N): "
            read confirm
            if [[ "$confirm" == "j" || "$confirm" == "J" ]]; then
                optimize_drive
            else
                echo -e "${YELLOW}Optimierung abgebrochen.${NC}"
            fi
            exit 0
            ;;
        -t|--test)
            test_performance
            exit 0
            ;;
        -a|--all-tests)
            echo -e "${RED}WARNUNG: Diese Option führt umfangreiche Tests durch und formatiert${NC}"
            echo -e "${RED}das Laufwerk mehrfach. Alle Daten auf ${DEVICE} werden gelöscht!${NC}"
            echo -n "Möchtest du fortfahren? (j/N): "
            read confirm
            if [[ "$confirm" == "j" || "$confirm" == "J" ]]; then
                test_all_fs
            else
                echo -e "${YELLOW}Tests abgebrochen.${NC}"
            fi
            exit 0
            ;;
        -s|--show)
            analyze_results
            exit 0
            ;;
        -m|--menu)
            # Weiter zum Menü
            ;;
        *)
            echo -e "${RED}Ungültige Option: $1${NC}"
            show_help
            exit 1
            ;;
    esac
fi

# Skript mit Menü starten
show_menu

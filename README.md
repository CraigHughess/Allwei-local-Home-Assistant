# Allwei Local — Home Assistant Integration

> Lokale Home Assistant Integration für **Allwei** Energiespeichersysteme.  
> Keine Cloud. Keine Subscription. Direkte TCP-Kommunikation im lokalen Netzwerk.

![Allwei Logo](www/local/allwei_local_plugin/logo.png)

---

## Überblick

Diese Integration verbindet Home Assistant **direkt** mit deinem Allwei Wechselrichter/Gateway über dein lokales Netzwerk — ohne dass Daten über einen Cloud-Server geleitet werden. Geräte werden automatisch via **mDNS/Zeroconf** erkannt (keine manuelle IP-Eingabe nötig).

### Was du bekommst

| Kategorie | Entitäten |
|---|---|
| **Systemübersicht** | Gesamte Wirkleistung, PV-Leistung, PV-Ladeleistung, AC-Ladeleistung, Smartload-Verbrauch, Batterie-SOC, Batterie-Ausgangsleistung, Netzleistung, Backup-Leistung |
| **Smarte Steckdosen** | Wirkleistung je Steckdose, Ein/Aus-Schalter |
| **Ladestation (EV)** | Connector 1 & 2 Status, Connector 1 & 2 Ladeleistung, Ein/Aus-Schalter |
| **Heizung / Warmwasser** | Wirkleistung, Max-Leistung, Temperatur, Max-Temperatur, Ein/Aus-Schalter |
| **Wechselrichter-Steuerung** | AC Off-Grid Relais, Maximale Einspeisung, Batterie-Entladung |

Alle Werte aktualisieren sich alle **10 Sekunden** direkt vom Gerät.

---

## Voraussetzungen

- Home Assistant **2023.4** oder neuer (auf Raspberry Pi oder anderem System)
- Allwei Gateway im **selben lokalen Netzwerk** wie deine HA-Installation
- Zugriff auf das HA-Dateisystem via **Samba Share**, **File Editor** oder **SSH** Add-on

---

## Installation

### Schritt 1 — Dateizugriff einrichten

Für die Installation musst du Dateien auf deinen Raspberry Pi übertragen. Nutze eine der folgenden Methoden:

- **Samba Share** Add-on: Einstellungen → Add-ons → Samba Share installieren & starten  
- **File Editor** Add-on: für direkte Bearbeitung im Browser  
- **Advanced SSH & Web Terminal** Add-on: für SSH-Zugriff

> Der `config`-Ordner auf dem Raspberry Pi entspricht dem HA-Konfigurationsverzeichnis (`~/.homeassistant/config/` bzw. `/homeassistant/`).

---

### Schritt 2 — Backend-Plugin installieren

1. Lade dieses Repository als ZIP herunter (oder klone es)
2. Prüfe ob der Ordner `config/custom_components/` existiert — falls nicht, erstelle ihn
3. Kopiere den Ordner `allwei_local_plugin` in `config/custom_components/`:

```
config/
└── custom_components/
    └── allwei_local_plugin/    ← hier einfügen
        ├── __init__.py
        ├── manifest.json
        ├── config_flow.py
        ├── coordinator.py
        ├── sensor.py
        ├── switch.py
        ├── tcp_client.py
        ├── tcp_manager.py
        └── const.py
```

4. Starte Home Assistant neu: **Einstellungen → System → Neustart**

---

### Schritt 3 — Gerät einrichten

**Automatische Erkennung (empfohlen)**

Das Plugin erkennt dein Allwei-Gerät automatisch über Zeroconf, sobald es im selben Netzwerk aktiv ist. Eine Benachrichtigung erscheint unter **Einstellungen → Geräte & Dienste**. Klicke auf **Konfigurieren**, vergib einen Namen und bestätige.

Die Erkennung zeigt:
- Geräte-Seriennummer
- Lokale IP-Adresse  
- Gerätetyp (Wechselrichter, Ladestation, Batterie, ...)

**Manuelle Einrichtung (falls automatische Erkennung fehlschlägt)**

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen**
2. Nach **Allwei Local** suchen
3. IP-Adresse und Port des Gateways eingeben (Standard-Port: `8899`)

---

## Entitäten-Referenz

### Sensoren

#### Systemübersicht (`SSumInfoList`)

| Entität | Einheit | Beschreibung |
|---|---|---|
| Total Active Power | W | Gesamte Wirkleistung (Zähler) |
| PV Power | W | Gesamte PV-Erzeugung |
| PV Charge Power | W | PV-Leistung in Batterie |
| AC Charge Power | W | Netzleistung in Batterie |
| Smart Load Power | W | Smartload-Verbrauch gesamt |
| Battery SOC | % | Durchschnittlicher Ladestand |
| Battery Output Power | W | Batterie-Entladeleistung |
| Grid Output Power | W | Netzeinspeisung / -bezug |
| Backup Power | W | Backup-Ausgangsleistung |

#### Pro Gerät (Steckdose / Ladestation / Heizung)

Entitäten werden dynamisch für jedes erkannte Sub-Gerät erstellt. Jedes Gerät erhält seine eigene Entität mit der Geräte-Seriennummer als Prefix.

### Schalter

#### Sub-Gerät Schalter
| Schalter | Beschreibung |
|---|---|
| `<PlugSN> Status` | Smarte Steckdose ein/aus |
| `<ChargerSN> Status` | Ladestation freigeben/sperren |
| `<HotSN> Status` | Heizung / Warmwasser ein/aus |

#### Wechselrichter Hardware-Schalter

Diese Schalter schreiben direkt in Hardware-Register des Wechselrichters — lokal, ohne Cloud-Umweg.

| Schalter | Register | Beschreibung |
|---|---|---|
| AC Off-Grid Mode | 123 | Off-Grid AC-Ausgang (Relais) |
| Max Feed-In Power | 124 | Maximale Einspeisung aktivieren |
| Battery Discharge | 125 | Batterie-Entladung global freigeben/sperren |

> **Hinweis:** Die Wechselrichter-Schalter nutzen optimistisches State-Tracking, falls das Gateway die entsprechenden Statusfelder (`ACRelayStatus`, `MaxFeedPowerFlag`, `BasicDisChargeEnable`) noch nicht im `EnergyParameter`-Response mitliefert. Nach dem ersten Schalten zeigt HA den gesendeten Befehl — beim nächsten Poll-Zyklus wird der echte Gerätestatus übernommen.

---

## Wie es funktioniert

```
Home Assistant
     │  JSON über TCP (LAN, Port 8899)
     ▼
Allwei Gateway  (automatisch erkannt via mDNS)
     │  RS485 / interner Bus
     ▼
Wechselrichter · Batterie · Steckdosen · Ladestation · Heizung
```

1. **Erkennung** — das Gateway sendet einen mDNS-Eintrag (`_http._tcp.local.`) mit Gerätemetadaten (SN, IP, Typ)
2. **Daten-Polling** — alle 10 s sendet die Integration `{"Get": "EnergyParameter"}` über eine persistente TCP-Verbindung und parst die JSON-Antwort
3. **Steuerung** — Sub-Geräte (Steckdosen, Ladestation, Heizung) via `{"Set": "SubDeviceControl"}`, Wechselrichter-Schalter via `{"Set": "InverterParam"}` mit Register-Adresse
4. **Reconnect** — bei Verbindungsabbruch verbindet sich die Integration automatisch wieder

---

## Unterstützte Gerätetypen

| Typ-Code | Gerät |
|---|---|
| 1 – 49 | Wechselrichter / Off-Grid / Speichereinheit |
| 50 – 54 | Energiezähler |
| 55 – 79 | EV-Ladestation |
| 80 – 109 | Batteriemodul |
| 110 – 139 | Smarte Steckdose |
| 141 – 145 | AC-Koppler |
| 150 – 155 | Warmwasser- / Heizungsregler |
| 156 – 160 | Relais |

---

## Fehlerbehebung

**Gerät wird nicht automatisch erkannt**
- Stelle sicher, dass Gateway und HA im selben Subnetz sind (mDNS funktioniert nicht über Subnetz-Grenzen)
- Prüfe, ob eine Firewall Multicast-Traffic blockiert
- Nutze die manuelle Einrichtung mit der Gateway-IP

**Entitäten zeigen "Nicht verfügbar"**
- HA-Logs öffnen und nach `allwei_local_plugin` filtern
- Der rohe TCP-Response wird auf `INFO`-Level geloggt — suche nach `Received raw response:` um zu sehen, was das Gateway zurückgibt
- Gateway-Port erreichbar prüfen: `nc -zv <gateway-ip> 8899`

**Wechselrichter-Schalter reagieren nicht**
- Das lokale Gateway muss `{"Set": "InverterParam"}` unterstützen — prüfe die Firmware-Version deines Gateways
- Alternativ sind Register-Adresse und gesendeter Wert als Extra-Attribute an jeder Switch-Entität sichtbar (zur Diagnose)

---

## Neue Sensoren hinzufügen

Der `EnergyParameter`-Response des Gateways enthält meist mehr Felder als aktuell gemappt. Um weitere Werte als Sensoren hinzuzufügen:

1. HA-Logs auf `INFO` setzen und nach `Received raw response:` suchen → JSON komplett auslesen
2. Gewünschtes Feld in `SENSOR_MAP` in `sensor.py` eintragen:
   ```python
   "SSumInfoList": {
       "mein_neuer_sensor": ("FeldNameImJSON", UnitOfPower.WATT),
   }
   ```
3. HA neu starten

---

## Geplante Features (Roadmap)

| Version | Geplant |
|---|---|
| **v1.1.0** | Wechselrichter-Schalter via lokales Gateway (AC Off-Grid, Max. Einspeisung, Batterie-Entladung) — sofern Firmware-Support vorhanden |
| **v1.2.0** | Energie-Statistiken (Tages-/Monatszähler), erweiterte Batterie-Diagnose |
| **Zukunft** | Konfigurierbare Poll-Intervalle, Mehrere Gateways gleichzeitig, Automatische Sensor-Erkennung aus dem kompletten EnergyParameter-Response |

---

## Versionsverlauf

| Version | Änderungen |
|---|---|
| 1.0.0 | Erstveröffentlichung — Auto-Erkennung via mDNS, Sensoren (Systemübersicht + Speicher-Detail), Sub-Gerät-Schalter (Steckdose, Ladestation, Heizung) |

---

## Bildnachweis

Das Logo (`www/local/allwei_local_plugin/logo.png`) stammt von der offiziellen Allwei-Website [allwei.de](https://www.allwei.de) und wird hier ausschließlich zur Wiedererkennbarkeit der Integration verwendet. Alle Marken- und Urheberrechte liegen bei den jeweiligen Eigentümern.

---

## Haftungsausschluss & Keine Zugehörigkeit

Dieses Projekt ist ein **unabhängiges Community-Projekt** und steht in **keinerlei Verbindung** mit der Allwei GmbH, deren Muttergesellschaft, Tochtergesellschaften oder Partnern. Es handelt sich weder um ein offizielles Produkt noch um eine offiziell unterstützte Lösung von Allwei.

Die Bezeichnung „Allwei" sowie zugehörige Logos und Markenzeichen sind Eigentum ihrer jeweiligen Inhaber. Die Nutzung in diesem Projekt erfolgt ausschließlich zur Identifikation der kompatiblen Hardware.

Die Verwendung dieser Integration erfolgt auf eigene Verantwortung. Der Autor übernimmt keine Haftung für Schäden an Geräten, Datenverlust oder andere Folgen, die durch den Einsatz dieser Software entstehen können.

---

## Lizenz

MIT

# Control the Wallbox through the Wiser Home cloud API

The EVlink Home Smart offers no documented local control: it keeps one outbound OCPP link to Schneider's backend, and its commissioning API answers only on its own access point. The integration therefore talks to the same cloud API as the Wiser Home app, which gives Start, Stop, session energy and state without touching the Wallbox's configuration, and keeps the Wiser Home app and TIC load management working as before. The cost is a dependency on a service Schneider may change or shut down, which we accept for as long as the app works.

## Considered Options

- **An OCPP relay between the Wallbox and Schneider's backend**, so Home Assistant sees the OCPP traffic and can send commands while the Wiser Home app keeps working. Rejected for now: it means changing the Wallbox's supervision URL, adds a single point of failure on the LAN, and nothing shows that Schneider's backend accepts a relayed link.
- **Pointing the Wallbox at a local OCPP central system** (such as the `ocpp` custom integration). This ends the Wiser Home app. It remains the idea for the day the cloud disappears, neither studied nor tested.

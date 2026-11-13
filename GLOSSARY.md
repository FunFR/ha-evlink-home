# EVlink Home

Home Assistant integration for the Schneider EVlink Home Smart wallbox, independent of the vendor's mobile apps.

## Language

### Hardware

**Wallbox**:
The Schneider EVlink Home Smart charging station (EVH4 range) wired to the house supply.
_Avoid_: Charger, borne, EVSE, charging point

**EVlink Home**:
The sibling model without any network interface, outside this project.
_Avoid_: EVlink Home basic, non-smart

### Power

**Subscribed power**:
The maximum apparent power of the household electricity contract, in kVA, as announced by the Linky meter's TIC.
_Avoid_: Contract power in kW, puissance souscrite in kW

**TIC load management**:
The Wallbox's own behaviour of lowering its charge current from the Linky historic TIC frames so the house stays under the Subscribed power.
_Avoid_: Load shedding, délestage, dynamic load balancing

### Charging

**Charge session**:
The period between a car being plugged into the Wallbox and being unplugged.
_Avoid_: Charge, transaction

**Start**:
Making the Wallbox charge the plugged-in car, whether it was waiting or stopped. The Wiser Home app's "Démarrer la charge".
_Avoid_: Resume, charge now, boost

**Stop**:
Interrupting charging while the Charge session goes on, so Start can charge again. The Wiser Home app's "Arrêter la charge".
_Avoid_: Pause, suspend, end

**Disable**:
Keeping the Wallbox from charging when a car is plugged in, until it is enabled again. Start still charges the plugged-in car. Not offered by the Wiser Home app.
_Avoid_: Lock, block, turn off

### Vendor apps

**Wiser Home app**:
Schneider's end-user mobile app that monitors and controls the Wallbox through Schneider's cloud.
_Avoid_: Wizer Home, SE Home

**eSetup app**:
Schneider's installer app that commissions the Wallbox locally, at installation time.
_Avoid_: ConfigElec, commissioning tool

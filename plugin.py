# A Python plugin for Domoticz to access looko2 api for smog information in Poland
#
# Author: rysi3k
# Original Author: fisher
#
# v0.1.0 - initial version, fetching data from looko2 sensor - based on airly
#
"""
<plugin key="looko2" name="domoticz-looko2" author="rysi3k" version="0.1.0" externallink="https://github.com/rysi3k/domoticz-looko2">
    <params>
		<param field="Mode1" label="LookO2 API key" default="" width="100px" required="true"  />
        <param field="Mode2" label="LookO2 sensor id" width="100px" default="" required="true" />
        <param field="Mode3" label="Check every x minutes" width="40px" default="20" required="true" />
		<param field="Mode6" label="Debug" width="75px">
			<options>
				<option label="True" value="Debug"/>
				<option label="False" value="Normal" default="true" />
			</options>
		</param>
    </params>
</plugin>
"""

import Domoticz
import datetime
import json
from urllib.request import urlopen
from urllib.parse import urlparse

L10N = {
    'pl': {
        "Air Quality Index":
            "Indeks Jakości Powietrza",
        "PM1":
            "PM1",
        "PM2,5":
            "PM2,5",
        "PM10":
            "PM10",
        "PM2,5 Norm":
            "PM2,5 Norma",
        "PM10 Norm":
            "PM10 Norma",
        "Air pollution Level":
            "Zanieczyszczenie powietrza",
        "Advice":
            "Wskazówki",
        "Temperature":
            "Temperatura",
        "Humidity":
            "Wilgotność",
        "Installation information":
            "Informacje o stacji",
        "Device Unit=%(Unit)d; Name='%(Name)s' already exists":
            "Urządzenie Unit=%(Unit)d; Name='%(Name)s' już istnieje",
        "Creating device Name=%(Name)s; Unit=%(Unit)d; ; TypeName=%(TypeName)s; Used=%(Used)d":
            "Tworzę urządzenie Name=%(Name)s; Unit=%(Unit)d; ; TypeName=%(TypeName)s; Used=%(Used)d",
        "%(Vendor)s - %(Address)s, %(Locality)s<br/>Station founder: %(sensorFounder)s":
            "%(Vendor)s - %(Address)s, %(Locality)s<br/>Sponsor stacji: %(sensorFounder)s",
        "%(Vendor)s - %(Locality)s %(StreetNumber)s<br/>Station founder: %(sensorFounder)s":
            "%(Vendor)s - %(Locality)s %(StreetNumber)s<br/>Sponsor stacji: %(sensorFounder)s",
        "Sensor id (%(installation_id)d) not exists":
            "Sensor (%(installation_id)d) nie istnieje",
        "Not authorized":
            "Brak autoryzacji",
        "Starting device update":
            "Rozpoczynanie aktualizacji urządzeń",
        "Update unit=%d; nValue=%d; sValue=%s":
            "Aktualizacja unit=%d; nValue=%d; sValue=%s",
        "Bad air today!":
            "Zła jakość powietrza",
        "Enter correct looko2 API key":
            "Wprowadź poprawny klucz api",
        "Awaiting next poll: %s":
            "Oczekiwanie na następne pobranie: %s",
        "Next poll attempt at: %s":
            "Następna próba pobrania: %s",
        "Connection to looko2 api failed: %s":
            "Połączenie z looko2 api nie powiodło się: %s",
        "Unrecognized error: %s":
            "Nierozpoznany błąd: %s"
    },
    'en': { }
}

def _(key):
    try:
        return L10N[Settings["Language"]][key]
    except KeyError:
        return key

class UnauthorizedException(Exception):
    def __init__(self, expression, message):
        self.expression = expression
        self.message = message

class SensorNotFoundException(Exception):
    def __init__(self, expression, message):
        self.expression = expression
        self.message = message

class ConnectionErrorException(Exception):
    def __init__(self, expression, message):
        self.expression = expression
        self.message = message

class BasePlugin:
    enabled = False

    def __init__(self):
        # Consts
        self.version = "0.1.0"

        self.debug = False
        self.inProgress = False

        # Do not change below UNIT constants!
        self.UNIT_AIR_QUALITY_INDEX     = 1
        self.UNIT_AIR_POLLUTION_LEVEL   = 2
        self.UNIT_PM1                   = 3
        self.UNIT_PM25                  = 4
        self.UNIT_PM10                  = 5
        self.UNIT_TEMPERATURE           = 6
        self.UNIT_HUMIDITY              = 8
        self.UNIT_AIR_POLLUTION_ADVICE  = 10

        self.UNIT_PM25_PERCENTAGE       = 11
        self.UNIT_PM10_PERCENTAGE       = 12

        self.UNIT_PM25_NORM             = 25
        self.UNIT_PM10_NORM             = 50

        # Icons
        self.iconName = "airly"

        self.nextpoll = datetime.datetime.now()
        return

    def onStart(self):
        Domoticz.Debug("onStart called")
        if Parameters["Mode6"] == 'Debug':
            self.debug = True
            Domoticz.Debugging(1)
        else:
            Domoticz.Debugging(0)
        # Api
        self.api_v2_installation_measurements = "http://api.looko2.com/?method=GetLOOKO&token="+Parameters["Mode1"] +"&id="+Parameters["Mode2"]

        Domoticz.Heartbeat(20)
        self.pollinterval = int(Parameters["Mode3"]) * 60

        if self.iconName not in Images: Domoticz.Image('icons.zip').Create()
        iconID = Images[self.iconName].ID

        self.variables = {
            self.UNIT_AIR_QUALITY_INDEX: {
                "Name":     _("Air Quality Index"),
                "TypeName": "Custom",
                "Options":  {"Custom": "1;%s" % "CAQI"},
                "Image":    iconID,
                "Used":     1,
                "nValue":   0,
                "sValue":   None,
            },
            self.UNIT_PM1: {
                "Name":     _("PM1"),
                "TypeName": "Custom",
                "Options":  {"Custom": "1;%s" % "µg/m³"},
                "Image":    iconID,
                "Used":     0,
                "nValue":   0,
                "sValue":   None,
            },
            self.UNIT_PM25: {
                "Name":     _("PM2,5"),
                "TypeName": "Custom",
                "Options":  {"Custom": "1;%s" % "µg/m³"},
                "Image":    iconID,
                "Used":     1,
                "nValue":   0,
                "sValue":   None,
            },
            self.UNIT_PM10: {
                "Name":     _("PM10"),
                "TypeName": "Custom",
                "Options":  {"Custom": "1;%s" % "µg/m³"},
                "Image":    iconID,
                "Used":     1,
                "nValue":   0,
                "sValue":   None,
            },
            self.UNIT_AIR_POLLUTION_LEVEL: {
                "Name":     _("Air pollution Level"),
                "TypeName": "Alert",
                "Image":    7,
                "Used":     1,
                "nValue":   0,
                "sValue":   None,
            },
            self.UNIT_AIR_POLLUTION_ADVICE: {
                "Name":     _("Advice"),
                "TypeName": "Alert",
                "Image":    7,
                "Used":     1,
                "nValue":   0,
                "sValue":   None,
            },
            self.UNIT_TEMPERATURE: {
                "Name":     _("Temperature"),
                "TypeName": "Temperature",
                "Used":     1,
                "nValue":   0,
                "sValue":   None,
            },
            self.UNIT_HUMIDITY: {
                "Name":     _("Humidity"),
                "TypeName": "Humidity",
                "Used":     1,
                "nValue":   0,
                "sValue":   None,
            },
            self.UNIT_PM25_PERCENTAGE: {
                "Name": _("PM2,5 Norm"),
                "TypeName": "Percentage",
                "Used": 1,
                "nValue": 0,
                "sValue": None,
            },
            self.UNIT_PM10_PERCENTAGE: {
                "Name": _("PM10 Norm"),
                "TypeName": "Percentage",
                "Used": 1,
                "nValue": 0,
                "sValue": None,
            },
        }

        self.onHeartbeat(fetch=True)

    def onStop(self):
        Domoticz.Log("onStop called")
        Domoticz.Debugging(0)

    def onConnect(self, Status, Description):
        Domoticz.Log("onConnect called")

    def onMessage(self, Data, Status, Extra):
        Domoticz.Log("onMessage called")

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Log(
            "onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Log("Notification: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(
            Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self):
        Domoticz.Log("onDisconnect called")

    def postponeNextPool(self, seconds=3600):
        self.nextpoll = (datetime.datetime.now() + datetime.timedelta(seconds=seconds))
        return self.nextpoll

    def createDevice(self, key=None):
        """create Domoticz virtual device"""

        def createSingleDevice(key):
            """inner helper function to handle device creation"""

            item = self.variables[key]
            _unit = key
            _name = item['Name']

            # skip if already exists
            if key in Devices:
                Domoticz.Debug(_("Device Unit=%(Unit)d; Name='%(Name)s' already exists") % {'Unit': key, 'Name': _name})
                return

            try:
                _options = item['Options']
            except KeyError:
                _options = {}

            _typename = item['TypeName']

            try:
                _used = item['Used']
            except KeyError:
                _used = 0

            try:
                _image = item['Image']
            except KeyError:
                _image = 0

            Domoticz.Debug(_("Creating device Name=%(Name)s; Unit=%(Unit)d; ; TypeName=%(TypeName)s; Used=%(Used)d") % {
                               'Name':     _name,
                               'Unit':     _unit,
                               'TypeName': _typename,
                               'Used':     _used,
                           })

            Domoticz.Device(
                Name=_name,
                Unit=_unit,
                TypeName=_typename,
                Image=_image,
                Options=_options,
                Used=_used
            ).Create()

        if key:
            createSingleDevice(key)
        else:
            for k in self.variables.keys():
                createSingleDevice(k)

    def onHeartbeat(self, fetch=False):
        Domoticz.Debug("onHeartbeat called")
        now = datetime.datetime.now()

        if fetch == False:
            if self.inProgress or (now < self.nextpoll):
                Domoticz.Debug(_("Awaiting next pool: %s") % str(self.nextpoll))
                return

        # Set next pool time
        self.postponeNextPool(seconds=self.pollinterval)

        try:
            # check if another thread is not running
            # and time between last fetch has elapsed
            self.inProgress = True

            res = self.installation_measurement(Parameters["Mode2"])

        
            try:
                self.variables[self.UNIT_PM10]['sValue'] = res["PM10"]
                self.variables[self.UNIT_PM10_PERCENTAGE]['sValue'] = (int(res["PM10"])/self.UNIT_PM10_NORM) * 100
            except KeyError:
                pass  # No pm10 value

            try:
                self.variables[self.UNIT_PM25]['sValue'] = res["PM25"]
                self.variables[self.UNIT_PM25_PERCENTAGE]['sValue'] = (int(res["PM25"]) / self.UNIT_PM25_NORM) * 100
            except KeyError:
                pass  # No pm25 value

            try:
                self.variables[self.UNIT_PM1]['sValue'] = res["PM1"]
            except KeyError:
                pass  # No pm1 value

            try:
                self.variables[self.UNIT_AIR_QUALITY_INDEX]['sValue'] = res["IJP"]
            except KeyError:
                pass  # No IJP value

            try:
                if res["IJP"] == "VERY_LOW":
                    pollutionLevel = 1  # green
                elif res["IJP"] == "LOW":
                    pollutionLevel = 1  # green
                elif res["IJP"] == "MEDIUM":
                    pollutionLevel = 2  # yellow
                elif res["IJP"] == "HIGH":
                    pollutionLevel = 3  # orange
                elif res["IJP"] == "EXTREME":
                    pollutionLevel = 4  # red
                elif res["IJP"] == "AIRMAGEDDON":
                    pollutionLevel = 4  # red
                else:
                    pollutionLevel = 0
                
                pollutionDescription = res["IJPDescription"]
                pollutionAdvice = res["IJPString"]

                self.variables[self.UNIT_AIR_POLLUTION_LEVEL]['nValue'] = pollutionLevel
                self.variables[self.UNIT_AIR_POLLUTION_LEVEL]['sValue'] = pollutionDescription
                
                self.variables[self.UNIT_AIR_POLLUTION_ADVICE]['nValue'] = pollutionLevel
                self.variables[self.UNIT_AIR_POLLUTION_ADVICE]['sValue'] = pollutionAdvice
                
            except KeyError:
                pass  # No air pollution value

            try:
                humidity = int(res["Humidity"])
                if humidity < 40:
                    humidity_status = 2  # dry HUMIDITY
                elif 40 <= humidity <= 60:
                    humidity_status = 0  # normal HUMIDITY
                elif 40 < humidity <= 70:
                    humidity_status = 1  # comfortable HUMIDITY
                else:
                    humidity_status = 3  # wet HUMIDITY

                self.variables[self.UNIT_HUMIDITY]['nValue'] = humidity
                self.variables[self.UNIT_HUMIDITY]['sValue'] = str(humidity_status)
            except KeyError:
                pass  # No humidity value

            try:
                self.variables[self.UNIT_TEMPERATURE]['sValue'] = res["Temperature"]
            except KeyError:
                pass  # No temperature value

            self.doUpdate()
        except SensorNotFoundException as snfe:
            Domoticz.Error(_("Sensor id (%(installation_id)d) not exists") % {'installation_id': Parameters["Mode2"]})
            return
        except UnauthorizedException as ue:
            Domoticz.Error(ue.message)
            Domoticz.Error(_("Enter correct looko2 API key"))
            return
        except ConnectionErrorException as cee:
            Domoticz.Error(_("Connection to looko2 api failed: %s") % str(cee.message))
            return
        except Exception as e:
            Domoticz.Error(_("Unrecognized error: %s") % str(e))
        finally:
            self.inProgress = False

    def doUpdate(self):
        Domoticz.Log(_("Starting device update"))
        for unit in self.variables:
            nV = self.variables[unit]['nValue']
            sV = self.variables[unit]['sValue']

            # cast float to str
            if isinstance(sV, float):
                sV = str(float("{0:.0f}".format(sV))).replace('.', ',')

            # Create device if required
            if sV:
                self.createDevice(key=unit)
                if unit in Devices:
                    Domoticz.Log(_("Update unit=%d; nValue=%d; sValue=%s") % (unit, nV, sV))
                    Devices[unit].Update(nValue=nV, sValue=sV)

    def installation_measurement(self, installation_id):
        """current sensor measurements"""

        try:
            response = urlopen(self.api_v2_installation_measurements)
            response_body = response.read()
        except Exception as e:
            raise ConnectionErrorException('', str(e))

        try:
            response_object = json.loads(response_body.decode("utf-8"))
        except UnicodeDecodeError as ude:
            Domoticz.Error(str(ude.message))
            # reset nextpool datestamp to force running in next run
            self.postponeNextPool(seconds=0)

        if response.getcode() == 200:
            if "Device" in response_object and len(response_object['Device']) > 0:
                return response_object
            else:
                raise SensorNotFoundException(installation_id, "")
            return response_object
        elif response.getcode() in (401, 403, 404):
            raise UnauthorizedException(
                response.status,
                response_object
            )
        else:
            Domoticz.Error(
                str(response.getcode()) + ": " +
                response_object
            )

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Status, Description):
    global _plugin
    _plugin.onConnect(Status, Description)

def onMessage(Data, Status, Extra):
    global _plugin
    _plugin.onMessage(Data, Status, Extra)

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)

def onDisconnect():
    global _plugin
    _plugin.onDisconnect()

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

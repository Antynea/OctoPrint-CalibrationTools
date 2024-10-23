# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import re
from threading import Event

import flask
import octoprint.plugin

CMD_PID_SAVE = "pid_save"
CMD_PID_START = "pid_start"
CMD_PID_LOAD_CURRENT_VALUES = "pid_getCurrentValues"
CMD_PID_GET_VALUES = "pid_getValues"

#this regex matches:
# !!DEBUG:send echo: Kp: 30.56 Ki: 3.03 Kd: 77.16
# !!DEBUG:send Kp: 30.56 Ki: 3.03 Kd: 77.16
# !!DEBUG:send echo: p:18.84 i:1.18 d:201.41
# !!DEBUG:send p:18.84 i:1.18 d:201.41
# !!DEBUG:send echo: M304 P131.06 I11.79 D971.23
# !!DEBUG:send M304 P131.06 I11.79 D971.23
allPIDsFormats = r".*p:{0,1}\s{0,1}?(?P<p>\d{1,4}\.\d{1,4})\s*i:{0,1}\s{0,1}?(?P<i>\d{1,4}\.\d{1,4})\s*d:{0,1}\s{0,1}?(?P<d>\d{1,4}\.\d{1,4})"

class API(octoprint.plugin.SimpleApiPlugin):
    pidHotEndCycles = []
    pidCurrentValues = {}
    pidHotEndCycles = {
        "hotEnd": [],
        "bed":[]
    }
    #catch for "echo: p:28.27 i:2.82 d:70.81"  or   "M301 P27.08 I2.51 D73.09"
    getPid = re.compile(allPIDsFormats, flags=re.IGNORECASE)
    @staticmethod
    def apiCommands():
        return {
            CMD_PID_LOAD_CURRENT_VALUES: [],
            CMD_PID_SAVE : [],
            CMD_PID_GET_VALUES: [],
            CMD_PID_START: ["heater", "fanSpeed", "noCycles", "hotEndIndex", "targetTemp"]
            }

    def apiGateWay(self, command, data):
        self._logger.debug("DIPGateway")
        if command == CMD_PID_LOAD_CURRENT_VALUES:
            # Créer des événements pour chaque commande afin de s'assurer que chaque réponse est reçue
            hasResult301 = Event()
            hasResult304 = Event()

            # Enregistrer les réponses pour hotEnd (M301)
            self.registerRegexMsg(self.getPid, self.m301_m304CodeResponse, hasResult301, "hotEnd")
            # Envoyer la commande M301 pour obtenir les valeurs PID du hotend
            self._logger.debug("Sending M301 command")
            self._printer.commands(["M301"])
            # Attendre la réponse de M301 avant d'envoyer la prochaine commande
            if not hasResult301.wait(5):  # Attendre jusqu'à 5 secondes
                self._logger.warning("Timeout waiting for M301 response")

            # Enregistrer les réponses pour bed (M304)
            self.registerRegexMsg(self.getPid, self.m301_m304CodeResponse, hasResult304, "bed")
            # Envoyer la commande M304 pour obtenir les valeurs PID du lit chauffant
            self._logger.debug("Sending M304 command")
            self._printer.commands(["M304"])
            # Attendre la réponse de M304 avant de continuer
            if not hasResult304.wait(5):  # Attendre jusqu'à 5 secondes
                self._logger.warning("Timeout waiting for M304 response")

            # Log des valeurs PID avant de renvoyer la réponse
            self._logger.debug("PID values before returning: %s", self.pidCurrentValues)

            return flask.jsonify({
                "data": {
                    "hotEnd": self.pidCurrentValues.get("hotEnd", {}),
                    "bed": self.pidCurrentValues.get("bed", {})
                }
            })

        if command == CMD_PID_START:
            self.pidHotEndCycles[data["heater"]] = []
            #Two cycles are for tuning
            for i in range(0, data['noCycles'] - 2):
                #response type !!DEBUG:send Kp: 30.56 Ki: 3.03 Kd: 77.16
                self.registerRegexMsg(self.getPid, self.m106CodeResponse, data["heater"])

            if data["heater"] == "bed":
                data["hotEndIndex"] = -1

            self._printer.commands(["M106 S%(fanSpeed)s" % data, "M303 C%(noCycles)s E%(hotEndIndex)s S%(targetTemp)s U1" % data, "M500"])

        if command == CMD_PID_SAVE:
            self._logger.debug("DIPSave-")
            return flask.jsonify({
                "data": self.pidCycles
            })
        if command == CMD_PID_GET_VALUES:
            self._logger.debug("pid_getValues-")
            return flask.jsonify({
                "data": self.pidCycles
            })

    @staticmethod
    def m301_m304CodeResponse(self, line, regex, event, storingKey):
        # Log pour voir ce qui est réellement reçu
        self._logger.debug("Received line for %s: %s", storingKey, line)

        # Vérifier si la réponse contient "Unknown command"
        if "Unknown command" in line:
            self._logger.warning(f"Received 'Unknown command' for {storingKey}: {line}")
            # Ajouter une notification à l'interface OctoPrint pour avertir l'utilisateur
            self._plugin_manager.send_plugin_message(self._identifier, {
                "type": "warning",
                "message": f"La commande {storingKey} (M301 ou M304) n'est pas prise en charge par votre imprimante."
            })
            if event:
                event.set()  # Libérer l'événement même en cas d'erreur
            return

        # Si c'est une réponse valide avec les PID (M301 ou M304)
        self._logger.debug("Attempting to match regex for %s", storingKey)
        match = regex.match(line)
        self._logger.debug(f"Regex match object for {storingKey}: {match}")
        if match:
            # Log des valeurs capturées
            self._logger.debug("Matched PID values for %s: P=%s, I=%s, D=%s", storingKey, match.group("p"), match.group("i"), match.group("d"))

            # Vérifie explicitement si la commande est pour le hotend ou le lit
            if storingKey == "hotEnd" and "M301" in line:
                self.pidCurrentValues["hotEnd"] = {
                    "P": match.group("p"),
                    "I": match.group("i"),
                    "D": match.group("d")
                }
            elif storingKey == "bed" and "M304" in line:
                self.pidCurrentValues["bed"] = {
                    "P": match.group("p"),
                    "I": match.group("i"),
                    "D": match.group("d")
                }
            else:
                # Log détaillé en cas de non-correspondance
                self._logger.warning("No valid PID values found for the expected key: %s in line: %s", storingKey, line)

            if event:
                event.set()
        else:
            # Log détaillé en cas de non-correspondance
            self._logger.warning("No match for PID values in line: %s", line)

    @staticmethod
    def m106CodeResponse(self, line, regex, storingKey):
        self._logger.debug("m106CodeResponse: %s", line)
        match = regex.match(line)
        if match:
            self.pidHotEndCycles[storingKey].append({
                "P": match.group("p"),
                "I": match.group("i"),
                "D": match.group("d")
            })
        self._logger.debug("cycles %s", self.pidHotEndCycles)

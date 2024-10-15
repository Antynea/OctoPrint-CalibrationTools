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

# This regex matches the PID responses:
allPIDsFormats = r".*p:?\s*(?P<p>-?\d+(\.\d+)?)\s*i:?\s*(?P<i>-?\d+(\.\d+)?)\s*d:?\s*(?P<d>-?\d+(\.\d+)?)"

class API(octoprint.plugin.SimpleApiPlugin):
    pidHotEndCycles = []
    pidCurrentValues = {
        "hotEnd": {},
        "bed": {}
    }
    pidHotEndCycles = {
        "hotEnd": [],
        "bed": []
    }
    # Regex for extracting PID values
    getPid = re.compile(allPIDsFormats, flags=re.IGNORECASE)

    @staticmethod
    def apiCommands():
        return {
            CMD_PID_LOAD_CURRENT_VALUES: [],
            CMD_PID_SAVE: [],
            CMD_PID_GET_VALUES: [],
            CMD_PID_START: ["heater", "fanSpeed", "noCycles", "hotEndIndex", "targetTemp"]
        }

    def apiGateWay(self, command, data):
        self._logger.debug("DIPGateway")
        
        if command == CMD_PID_LOAD_CURRENT_VALUES:
            hasResult301 = Event()
            hasResult304 = Event()

            # Enregistrer les réponses pour hotEnd (M301) et bed (M304)
            self.registerRegexMsg(self.getPid, self.m301_m304CodeResponse, hasResult301, "hotEnd")
            self.registerRegexMsg(self.getPid, self.m301_m304CodeResponse, hasResult304, "bed")

            # Envoie des commandes pour hotEnd et bed
            self._logger.debug("Sending M301 and M304 commands")
            self._printer.commands(["M301", "M304"])
            hasResult301.wait(5)
            hasResult304.wait(5)

            return flask.jsonify({
                "data": {
                    "hotEnd": self.pidCurrentValues.get("hotEnd", {}),
                    "bed": self.pidCurrentValues.get("bed", {})
                }
            })

        if command == CMD_PID_START:
            self.pidHotEndCycles[data["heater"]] = []
            # Two cycles are for tuning
            for i in range(0, data['noCycles'] - 2):
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

    def m301_m304CodeResponse(self, line, regex, event, storingKey):
        self._logger.debug("m301_m304CodeResponse: %s", line)

        # Vérifier si la réponse contient "Unknown command"
        if "Unknown command" in line:
            self._logger.warning(f"Received 'Unknown command' for {storingKey}: {line}")
            if event:
                event.set()  # Libérer l'événement même en cas d'erreur
            return

        # Si c'est une réponse valide avec les PID (M301 ou M304)
        match = regex.match(line)
        if match:
            self.pidCurrentValues[storingKey] = {
                "P": match.group("p"),
                "I": match.group("i"),
                "D": match.group("d")
            }
            if event:
                event.set()

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

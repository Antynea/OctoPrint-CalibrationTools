# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import re
from threading import Event

import flask
import octoprint.plugin
import threading

CMD_PID_SAVE = "pid_save"
CMD_PID_START = "pid_start"
CMD_PID_LOAD_CURRENT_VALUES = "pid_getCurrentValues"
CMD_PID_GET_VALUES = "pid_getValues"

# Nouvelle expression régulière pour correspondre à la réponse M304, avec prise en compte des espaces
allPIDsFormats = r".*P(?P<p>-?\d+(\.\d+)?)\s+I(?P<i>-?\d+(\.\d+)?)\s+D(?P<d>-?\d+(\.\d+)?)"

class API(octoprint.plugin.SimpleApiPlugin):
    pidCurrentValues = {
        "hotEnd": {},
        "bed": {}
    }
    pidHotEndCycles = {
        "hotEnd": [],
        "bed": []
        }
    gCodeWaiters = []

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

        # Log avant de matcher le regex
        self._logger.debug("Attempting to match regex for %s", storingKey)

        # Si c'est une réponse valide avec les PID (M301 ou M304)
        match = regex.match(line)
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

    def registerRegexMsg(self, regex, func, *arguments):
        if regex is None or func is None:
            self._logger.warn("registerRegexMsg: Attempt to register gCodeAnswer without a function or regex")
            return

        self.gCodeWaiters.append({
            "regex": regex,
            "func": func,
            "args": arguments,
            "callCount": 0
        })

        # Ajouter un log pour confirmer l'enregistrement
        self._logger.debug("Registered regex: %s with function: %s", regex.pattern, func)

    def gCodeReceived(self, comm, line, *args, **kwargs):
        # Log chaque ligne reçue de l'imprimante
        self._logger.debug("Received gcode line: %s", line)

        # Parcourir tous les "gCodeWaiters" enregistrés pour voir s'il y a une correspondance
        for waiter in self.gCodeWaiters:
            if waiter["regex"].match(line):
                self._logger.debug("Matching line: %s with regex: %s", line, waiter["regex"].pattern)
                threading.Thread(target=waiter["func"], args=(line, waiter["regex"], *waiter["args"])).start()

        return line

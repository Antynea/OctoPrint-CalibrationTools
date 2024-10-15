$(function () {
    function CalibrationToolsPIDTuneViewModel(parameters) {
        var self = this;
        self.loginStateViewModel = parameters[0];
        self.settingsViewModel = parameters[1];
        self.controlViewModel = parameters[2];
        self.generalVM = parameters[5];
        self.columnLabelCls = ko.computed(function () {
            return self.generalVM.isSmall() ? "span3" : "span3";
        });
        self.columnFieldCls = ko.computed(function () {
            return self.generalVM.isSmall() ? "span9" : "span9";
        });
        self.pidCurrentValues = {
            "hotEnd": {
                "P": ko.observable(0),
                "I": ko.observable(0),
                "D": ko.observable(0)
            },
            "bed": {
                "P": ko.observable(0),
                "I": ko.observable(0),
                "D": ko.observable(0)
            }
        };

        self.isAdmin = ko.observable(false);
        self.pid = {
            "hotEnd": {
                fanSpeed: ko.observable(255),
                noCycles: ko.observable(8),
                hotEndIndex: ko.observable(0),
                targetTemp: ko.observable(200)
            },
            "bed": {
                fanSpeed: ko.observable(255),
                noCycles: ko.observable(8),
                index: ko.observable(-1),
                targetTemp: ko.observable(200)
            }
        };

        /**
         * Get current PIDs settings for bed and hotEnd
         */
        self.getCurrentValues = function () {
            console.log("The 'Get Current Value' command has started.");
            self.generalVM.notifyInfo("The 'Get Current Value' command has started.", "In Progress");

            OctoPrint.simpleApiCommand("CalibrationTools", "pid_getCurrentValues").done(function (response) {
                console.log("Received response:", response);  // Ajouté pour voir la réponse complète

                let missingValues = [];

                // Vérifier et assigner les valeurs PID pour le hotEnd
                if (response.data && response.data.hotEnd) {
                    const hotEndP = response.data.hotEnd.P;
                    const hotEndI = response.data.hotEnd.I;
                    const hotEndD = response.data.hotEnd.D;

                    if (hotEndP && hotEndI && hotEndD) {
                        self.pidCurrentValues.hotEnd.P(hotEndP);
                        self.pidCurrentValues.hotEnd.I(hotEndI);
                        self.pidCurrentValues.hotEnd.D(hotEndD);
                    } else {
                        missingValues.push("HotEnd PID values");
                    }
                } else {
                    missingValues.push("HotEnd PID values");
                }

                // Vérifier et assigner les valeurs PID pour le bed
                if (response.data && response.data.bed) {
                    const bedP = response.data.bed.P;
                    const bedI = response.data.bed.I;
                    const bedD = response.data.bed.D;

                    if (bedP && bedI && bedD) {
                        self.pidCurrentValues.bed.P(bedP);
                        self.pidCurrentValues.bed.I(bedI);
                        self.pidCurrentValues.bed.D(bedD);
                    } else {
                        missingValues.push("Bed PID values");
                    }
                } else {
                    missingValues.push("Bed PID values");
                }

                // Afficher un message en fonction des résultats
                if (missingValues.length === 0) {
                    self.generalVM.notify("PID values successfully updated.", "Success", "success");
                } else {
                    const warningMessage = `Warning: Some PID values are missing: ${missingValues.join(", ")}. Please verify the printer's response.`;
                    self.generalVM.notifyWarning(warningMessage, "Warning");
                }
            }).fail(function () {
                self.generalVM.notifyError("Failed to retrieve PID values. Please check the printer connection.", "Error");
            });
        };



        self.onBeforeBinding = self.onUserLoggedIn = self.onUserLoggedOut = function () {
            self.pid.hotEnd.fanSpeed(self.settingsViewModel.settings.plugins.CalibrationTools.pid.hotEnd.fanSpeed());
            self.pid.hotEnd.hotEndIndex(self.settingsViewModel.settings.plugins.CalibrationTools.pid.hotEnd.hotEndIndex());
            self.pid.hotEnd.noCycles(self.settingsViewModel.settings.plugins.CalibrationTools.pid.hotEnd.noCycles());
            self.pid.hotEnd.targetTemp(self.settingsViewModel.settings.plugins.CalibrationTools.pid.hotEnd.targetTemp());
            self.pid.bed.index(-1);
            self.pid.bed.noCycles(self.settingsViewModel.settings.plugins.CalibrationTools.pid.bed.noCycles());
            self.pid.bed.targetTemp(self.settingsViewModel.settings.plugins.CalibrationTools.pid.bed.targetTemp());
        }

        self.startPidHotEnd = function () {
            OctoPrint.simpleApiCommand("CalibrationTools", "pid_start", {
                "heater": "hotEnd",
                "fanSpeed": Number(self.pid.hotEnd.fanSpeed()),
                "noCycles": Number(self.pid.hotEnd.noCycles()),
                "hotEndIndex": Number(self.pid.hotEnd.hotEndIndex()),
                "targetTemp": Number(self.pid.hotEnd.targetTemp())
            }).done(function (response) {
                self.generalVM.notifyWarning("PID HotEnd tuning has started", "In progress");
            }).fail(self.generalVM.failFunction);
        }
        self.startPidBed = function () {
            OctoPrint.simpleApiCommand("CalibrationTools", "pid_start", {
                "heater": "bed",
                "fanSpeed": self.pid.bed.fanSpeed(),
                "noCycles": self.pid.bed.noCycles(),
                "hotEndIndex": -1,
                "targetTemp": self.pid.bed.targetTemp()
            }).done(function (response) {
                self.generalVM.notifyWarning("PID Heated bed tuning has started", "In progress");
            }).fail(self.generalVM.failFunction);
        }
    }
    OCTOPRINT_VIEWMODELS.push({
        // This is the constructor to call for instantiating the plugin
        construct: CalibrationToolsPIDTuneViewModel,
        // This is a list of dependencies to inject into the plugin, the order which you request
        // here is the order in which the dependencies will be injected into your view model upon
        // instantiation via the parameters argument
        dependencies: ["loginStateViewModel", "settingsViewModel", "controlViewModel", "terminalViewModel", "accessViewModel", "calibrationToolsGeneralViewModel"],
        // Finally, this is the list of selectors for all elements we want this view model to be bound to.
        elements: ["#calibration_pid"]
    });
});

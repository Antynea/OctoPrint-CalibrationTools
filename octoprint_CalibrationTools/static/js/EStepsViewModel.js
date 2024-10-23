$(function () {
    function CalibrationToolsEStepsModelView(parameters) {
        var self = this;

        self.loginStateViewModel = parameters[0];
        self.settingsViewModel = parameters[1];
        self.controlViewModel = parameters[2];
        self.terminalViewModel = parameters[3];
        self.access = parameters[4];
        self.generalVM = parameters[5];

        // Variable to indicate whether the steps have been loaded
        self.stepsLoaded = ko.observable(false);

        // Computed observables for column classes
        self.columnLabelCls = ko.computed(function () {
            const value = self.generalVM.isSmall() ? "span4" : "span3";
            console.debug("Computed columnLabelCls value:", value);
            return value;
        });
        self.columnFieldCls = ko.computed(function () {
            const value = self.generalVM.isSmall() ? "span8" : "span9";
            console.debug("Computed columnFieldCls value:", value);
            return value;
        });

        // Initialization of observables for steps
        self.steps = {
            X: ko.observable(),
            Y: ko.observable(),
            Z: ko.observable(),
            E: ko.observable()
        };

        // Initialization of test parameters with default values or localStorage values
        self.testParam = {
            extrudeTemp: ko.observable(parseInt(localStorage.getItem("extrudeTemp")) || 200),
            extrudeLength: ko.observable(parseInt(localStorage.getItem("extrudeLength")) || 100),
            extrudeSpeed: ko.observable(parseInt(localStorage.getItem("extrudeSpeed")) || 100),
            markLength: ko.observable(parseFloat(localStorage.getItem("markLength")) || 120)
        };

        // Initialization of results
        self.results = {};
        self.results["remainedLength"] = ko.observable(20);
        self.results["actualExtrusion"] = ko.computed(function () {
            const actual = self.generalVM.round(self.testParam.markLength() - self.results.remainedLength());
            console.debug("Computed actualExtrusion value:", actual);
            return actual;
        });
        self.results["newSteps"] = ko.computed(function () {
            if (!self.stepsLoaded()) {
                console.warn("Steps not loaded, returning 'N/A'");
                return "N/A"; // Or use `undefined` to make it explicit that the calculation has not yet taken place
            }
            const actualExtrusion = self.results.actualExtrusion();
            const eStep = self.steps.E();
            if (actualExtrusion === 0 || eStep === 0) {
                console.warn("Division by zero detected, returning 'N/A'");
                return "N/A"; // To avoid division by zero
            }
            const steps = self.generalVM.round((eStep * self.testParam.extrudeLength()) / actualExtrusion);
            console.debug("Computed newSteps value:", steps);
            return steps;
        });
        
        // Watch for changes in the parameters and save them in localStorage
        self.testParam["extrudeTemp"].subscribe(function (newValue) {
            console.info("Saving extrudeTemp:", newValue);
            localStorage.setItem("extrudeTemp", newValue);
        });
        self.testParam["extrudeLength"].subscribe(function (newValue) {
            console.info("Saving extrudeLength:", newValue);
            localStorage.setItem("extrudeLength", newValue);
        });
        self.testParam["extrudeSpeed"].subscribe(function (newValue) {
            console.info("Saving extrudeSpeed:", newValue);
            localStorage.setItem("extrudeSpeed", newValue);
        });
        self.testParam["markLength"].subscribe(function (newValue) {
            console.info("Saving markLength:", newValue);
            localStorage.setItem("markLength", newValue);
        });
        
        // Function to load parameters during binding
        self.onBeforeBinding = function () {
            console.log("Loading parameters from localStorage during binding...");
            OctoPrint.socket.onMessage("plugin.CalibrationTools", self.onDataUpdaterPluginMessage);
            // Load values from localStorage, and use default values if they do not exist
            const extrudeTemp = parseInt(localStorage.getItem("extrudeTemp"));
            const extrudeLength = parseInt(localStorage.getItem("extrudeLength"));
            const extrudeSpeed = parseInt(localStorage.getItem("extrudeSpeed"));
            const markLength = parseFloat(localStorage.getItem("markLength"));

            console.debug("Loaded extrudeTemp:", extrudeTemp);
            console.debug("Loaded extrudeLength:", extrudeLength);
            console.debug("Loaded extrudeSpeed:", extrudeSpeed);
            console.debug("Loaded markLength:", markLength);

            // Set the observables with the validated values or default values
            self.testParam.extrudeTemp(isNaN(extrudeTemp) ? 200 : extrudeTemp);
            self.testParam.extrudeLength(isNaN(extrudeLength) ? 100 : extrudeLength);
            self.testParam.extrudeSpeed(isNaN(extrudeSpeed) ? 100 : extrudeSpeed);
            self.testParam.markLength(isNaN(markLength) ? 120 : markLength);
        };

        // Function to process the JSON response and update the steps
        self.from_json = function (response) {
            console.log("M92 data:", response); // Ajoutez ceci pour vérifier les données de la réponse
            if (response && response.data) {
                self.steps.X(response.data.X || 0);
                self.steps.Y(response.data.Y || 0);
                self.steps.Z(response.data.Z || 0);
                self.steps.E(response.data.E || 0);

                console.debug("Updated steps: X:", self.steps.X(), "Y:", self.steps.Y(), "Z:", self.steps.Z(), "E:", self.steps.E());


                // Check if the steps have non-zero values before setting stepsLoaded to true
                if (response.data.X !== 0 || response.data.Y !== 0 || response.data.Z !== 0 || response.data.E !== 0) {
                    console.info("Steps loaded successfully.");
                    self.stepsLoaded(true); // Mark steps as loaded only if values are valid
                } else {
                    console.warn('Step values are all zero, "Save the new value" button remains inactive');
                    self.stepsLoaded(false);
                }
            } else {
                // If no response data, reset values to zero
                console.warn("No response data, resetting step values to zero.");
                self.steps.X(0);
                self.steps.Y(0);
                self.steps.Z(0);
                self.steps.E(0);
                self.stepsLoaded(false);
            }
        };

        // Load the current steps
        self.loadEStepsActive = ko.observable(true);
        self.loadESteps = function () {
            console.info("Loading E-Steps...");
            self.loadEStepsActive(false);
            OctoPrint.simpleApiCommand("CalibrationTools", "eSteps_load").done(function (response) {
                console.debug("eSteps_load response:", response);
                self.from_json(response);
            }).always(function (response) {
                console.info("E-Steps load process completed.");
                self.loadEStepsActive(true);
            });
        };

        // Start extrusion
        self.startExtrusionActive = ko.observable(false);
        self.startExtrusion = function () {
            if (self.startExtrusionActive()) {
                // Extrusion déjà en cours, ne rien faire
                console.warn("Extrusion already in progress, startExtrusion call ignored.");
                return;
            }
            console.info("Starting extrusion with parameters:", {
                extrudeTemp: self.testParam.extrudeTemp(),
                extrudeLength: self.testParam.extrudeLength(),
                extrudeSpeed: self.testParam.extrudeSpeed()
            });
            self.startExtrusionActive(true);
            OctoPrint.simpleApiCommand("CalibrationTools", "eSteps_startExtrusion", {
                "extrudeTemp": self.testParam.extrudeTemp(),
                "extrudeLength": self.testParam.extrudeLength(),
                "extrudeSpeed": self.testParam.extrudeSpeed()
            }).done(function (response) {
                console.debug("eSteps_startExtrusion response:", response);
                self.generalVM.notify(
                    "E-steps calibration started",
                    "<span style='font-weight:bold; color: red;'>Heating nozzle has started!</span><br> Extrusion is in progress. You have to fill in <b>Length after extrusion</b> and save the new value",
                    "warning",
                    true
                );
            }).fail(function (response) {
                console.error("Error during eSteps_startExtrusion call:", response.responseJSON.error);
                self.generalVM.notifyError("Error on starting extrusion ", response.responseJSON.error);
                self.startExtrusionActive(false);
            });
        };

        self.onDataUpdaterPluginMessage = function (plugin, data) {
            if (plugin !== "CalibrationTools") {
                return;
            }

            if (data.state === "extrusion_completed") {
                console.info("Extrusion completed, reactivating buttons...");
                self.startExtrusionActive(false);  // Réactivation du bouton d'extrusion
            }
        };

        // Stop extrusion
        self.stopExtrusion = function () {
            if (!self.startExtrusionActive()) {
                // Si l'extrusion n'est pas active, ne rien faire
                console.warn("Extrusion not active, stopExtrusion call ignored.");
                return; // Sortir de la fonction pour éviter l'appel API inutile
            }
            console.info("Stopping extrusion...");
            OctoPrint.simpleApiCommand("CalibrationTools", "eSteps_stopExtrusion")
                .done(function (response) {
                    console.debug("eSteps_stopExtrusion response:", response);
                    self.generalVM.notifyInfo("Extrusion stopped", "The extrusion process has been successfully stopped.");
                    self.startExtrusionActive(false);
                })
                .fail(function (response) {
                    console.error("Error during eSteps_stopExtrusion call:", response.responseJSON.error);
                    self.generalVM.notifyError("Error on stopping extrusion", response.responseJSON.error);
                });
        };

        self.resetValues = function() {
            console.log("Réinitialisation des valeurs...");

            // Réinitialiser les observables à leurs valeurs par défaut
            self.testParam.extrudeTemp(200);
            self.testParam.extrudeLength(100);
            self.testParam.extrudeSpeed(100);
            self.testParam.markLength(120);

            // Réinitialiser le localStorage avec les mêmes valeurs par défaut
            localStorage.setItem('extrudeTemp', 200);
            localStorage.setItem('extrudeLength', 100);
            localStorage.setItem('extrudeSpeed', 100);
            localStorage.setItem('markLength', 120);

            console.log("Valeurs réinitialisées et localStorage mis à jour.");
        };
        // Save the modified steps
        self.saveESteps = function () {
            console.info("Saving new eSteps value:", self.results.newSteps());
            OctoPrint.simpleApiCommand("CalibrationTools", "eSteps_save", {
                "newESteps": self.results.newSteps()
            }).done(function () {
                console.info("E-Steps saved successfully.");
                self.generalVM.notifyInfo("Saved", self.results.newSteps() + " steps/mm had been set for E steps");
            }).fail(function (response) {
                console.error("Error during eSteps_save call:", response);
                self.generalVM.failedFunction(response);
            });
        };
    }

    // Register the plugin with OctoPrint
    OCTOPRINT_VIEWMODELS.push({
        construct: CalibrationToolsEStepsModelView,
        dependencies: ["loginStateViewModel", "settingsViewModel", "controlViewModel", "terminalViewModel", "accessViewModel", "calibrationToolsGeneralViewModel"],
        elements: ["#calibration_eSteps"]
    });
});

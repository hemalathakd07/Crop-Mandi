/**
 * Farmer-facing dashboard greeting, weather, alerts, and saved predictions.
 */
(function (global) {
  "use strict";

  var ALERTS_KEY = "cropmandi_alerts";
  var PREDICTIONS_KEY = "cropmandi_saved_predictions";
  var lastWeatherSeq = 0;

  function $(id) {
    return document.getElementById(id);
  }

  function greetingPhrase(date) {
    var hour = date.getHours();
    if (hour >= 5 && hour < 12) {
      return "Good morning";
    }
    if (hour >= 12 && hour < 17) {
      return "Good afternoon";
    }
    if (hour >= 17 && hour < 21) {
      return "Good evening";
    }
    return "Good night";
  }

  function applyGreeting() {
    var el = $("dash-greeting");
    if (!el) {
      return;
    }
    var name = window.CropMandiAuth ? CropMandiAuth.firstName() : "Hemalatha";
    el.textContent = greetingPhrase(new Date()) + ", " + name;
  }

  function readList(key) {
    try {
      var raw = localStorage.getItem(key);
      var list = raw ? JSON.parse(raw) : [];
      return Array.isArray(list) ? list : [];
    } catch (err) {
      return [];
    }
  }

  function writeList(key, list) {
    localStorage.setItem(key, JSON.stringify(list));
  }

  function selectedContext() {
    var cropEl = $("dash-crop");
    var seriesEl = $("dash-series");
    var locationEl = $("dash-location");
    var cropValue = cropEl ? cropEl.value : "";
    var cropLabel = cropEl && cropEl.options[cropEl.selectedIndex]
      ? cropEl.options[cropEl.selectedIndex].textContent
      : cropValue;
    return {
      crop: cropValue,
      cropLabel: cropLabel,
      variety: seriesEl ? seriesEl.value : "",
      location: locationEl ? locationEl.value : "",
    };
  }

  function currentPriceText() {
    var el = $("dash-latest-price");
    return el ? String(el.textContent || "").trim() : "";
  }

  function predictedPriceText() {
    var el = $("dash-est-next-price");
    return el ? String(el.textContent || "").trim() : "";
  }

  function setActionFeedback(message, isError) {
    var el = $("dash-action-feedback");
    if (!el) {
      return;
    }
    el.textContent = message || "";
    el.classList.toggle("hidden", !message);
    el.classList.toggle("text-error", !!isError);
    el.classList.toggle("text-primary", !isError);
  }

  function weatherUnavailable() {
    var tempEl = $("dash-weather-temp");
    var descEl = $("dash-weather-desc");
    var humEl = $("dash-weather-humidity");
    var noteEl = $("dash-weather-note");
    if (tempEl) {
      tempEl.textContent = "";
    }
    if (descEl) {
      descEl.textContent = "Weather unavailable";
    }
    if (humEl) {
      humEl.textContent = "";
    }
    if (noteEl) {
      noteEl.textContent = "Weather unavailable";
    }
  }

  function loadWeather() {
    var locationEl = $("dash-location");
    var location = locationEl ? locationEl.value : "";
    if (!location || !window.CropMandiAPI || !CropMandiAPI.getWeather) {
      weatherUnavailable();
      return;
    }
    var seq = ++lastWeatherSeq;
    CropMandiAPI.getWeather(location)
      .then(function (payload) {
        if (seq !== lastWeatherSeq) {
          return;
        }
        if (!payload || payload.available === false || payload.temperature_c === undefined || payload.temperature_c === null) {
          weatherUnavailable();
          return;
        }
        var tempEl = $("dash-weather-temp");
        var descEl = $("dash-weather-desc");
        var humEl = $("dash-weather-humidity");
        var noteEl = $("dash-weather-note");
        if (tempEl) {
          tempEl.textContent = Math.round(Number(payload.temperature_c)) + "°C";
        }
        if (descEl) {
          descEl.textContent = payload.description || "";
        }
        if (humEl) {
          humEl.textContent =
            payload.humidity_percent === undefined || payload.humidity_percent === null
              ? ""
              : payload.humidity_percent + "% humidity";
        }
        if (noteEl) {
          noteEl.textContent = "Weather for " + (payload.location || location);
        }
      })
      .catch(function () {
        if (seq !== lastWeatherSeq) {
          return;
        }
        weatherUnavailable();
      });
  }

  function saveAlert() {
    var ctx = selectedContext();
    if (!ctx.crop || !ctx.variety || !ctx.location) {
      setActionFeedback("Select crop, variety, and location before setting an alert.", true);
      return;
    }
    var price = currentPriceText();
    var predicted = predictedPriceText();
    if (!price || price === "—" || price === "…" || price === "Data unavailable") {
      setActionFeedback("No current price available to set an alert.", true);
      return;
    }
    var alerts = readList(ALERTS_KEY);
    var item = {
      id: Date.now(),
      createdAt: new Date().toISOString(),
      crop: ctx.crop,
      cropLabel: ctx.cropLabel,
      variety: ctx.variety,
      location: ctx.location,
      currentPrice: price,
      predictedPrice: predicted,
    };
    alerts.unshift(item);
    writeList(ALERTS_KEY, alerts);
    setActionFeedback("Alert saved for " + ctx.cropLabel + " in " + ctx.location + ".");
  }

  function savePrediction() {
    var ctx = selectedContext();
    var estimate = global.CropMandiLastEstimate;
    if (!ctx.crop || !ctx.variety || !ctx.location) {
      setActionFeedback("Select crop, variety, and location before saving.", true);
      return;
    }
    if (!estimate || estimate.unavailable) {
      setActionFeedback("No prediction available to save.", true);
      return;
    }
    var saved = readList(PREDICTIONS_KEY);
    var item = {
      id: Date.now(),
      createdAt: new Date().toISOString(),
      crop: ctx.crop,
      cropLabel: ctx.cropLabel,
      variety: ctx.variety,
      location: ctx.location,
      currentPrice: estimate.latest_observed_price,
      predictedPrice: estimate.next_session_estimate,
      latestObservationDate: estimate.latest_observation_date || null,
      unit: estimate.unit || null,
    };
    saved.unshift(item);
    writeList(PREDICTIONS_KEY, saved);
    setActionFeedback("Prediction saved for " + ctx.variety + " in " + ctx.location + ".");
  }

  function init() {
    applyGreeting();
    var locationSelect = $("dash-location");
    if (locationSelect) {
      locationSelect.addEventListener("change", loadWeather);
      if (window.MutationObserver) {
        new MutationObserver(loadWeather).observe(locationSelect, {
          childList: true,
          attributes: true,
        });
      }
    }
    var refreshButton = $("dash-refresh");
    if (refreshButton) {
      refreshButton.addEventListener("click", loadWeather);
    }
    var alertBtn = $("dash-set-alert");
    if (alertBtn) {
      alertBtn.addEventListener("click", function (event) {
        event.preventDefault();
        saveAlert();
      });
    }
    var saveBtn = $("dash-save-prediction");
    if (saveBtn) {
      saveBtn.addEventListener("click", function (event) {
        event.preventDefault();
        savePrediction();
      });
    }
    loadWeather();
  }

  global.CropMandiDashboardUI = {
    applyGreeting: applyGreeting,
    loadWeather: loadWeather,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})(window);

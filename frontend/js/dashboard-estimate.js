/**
 * Next-session baseline estimate for the selected commodity series.
 * Uses GET /api/predictions/next. Does not invent prices or confidence.
 */
(function () {
  "use strict";

  var LOADING_MESSAGE = "Loading next-session estimate...";
  var ERROR_MESSAGE = "Unable to load the next-session estimate. Please try again.";
  var INSUFFICIENT_MESSAGE = "Prediction unavailable due to insufficient historical data.";
  var MONTHS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];

  var cropSelect;
  var seriesSelect;
  var locationSelect;
  var refreshButton;
  var statusEl;
  var errorEl;
  var bodyEl;
  var seriesEl;
  var locationEl;
  var latestPriceEl;
  var nextPriceEl;
  var latestDateEl;
  var targetEl;
  var unitEl;
  var methodEl;
  var modelStatusEl;
  var noteEl;
  var warningEl;
  var requestSeq = 0;

  function $(id) {
    return document.getElementById(id);
  }

  function commodity() {
    return cropSelect && cropSelect.value === "pepper" ? "pepper" : "coffee";
  }

  function selectedSeries() {
    return seriesSelect ? seriesSelect.value : "";
  }

  function formatPrice(value) {
    if (!Number.isFinite(value)) {
      return "—";
    }
    return "₹" + Number(value).toLocaleString("en-IN");
  }

  function formatDate(iso) {
    if (!iso) {
      return "Not yet known";
    }
    var parts = String(iso).split("-");
    if (parts.length !== 3) {
      return iso;
    }
    var monthIndex = Number(parts[1]) - 1;
    if (monthIndex < 0 || monthIndex > 11) {
      return iso;
    }
    return Number(parts[2]) + " " + MONTHS[monthIndex] + " " + parts[0];
  }

  function unitLabel(unit) {
    if (!unit) {
      return "—";
    }
    if (unit === "INR_PER_50KG") {
      return "Rs./50 Kg";
    }
    if (unit === "INR_PER_KG") {
      return "Rs./Kg";
    }
    return unit;
  }

  function setPredictionUnavailable(message) {
    window.CropMandiLastEstimate = { unavailable: true };
    var recCrop = $("dash-rec-crop");
    var recVariety = $("dash-rec-variety");
    if (recCrop) {
      recCrop.textContent = commodity() === "pepper" ? "Black Pepper" : "Coffee";
    }
    if (recVariety) {
      recVariety.textContent = selectedSeries() || "—";
    }
    if (nextPriceEl) {
      nextPriceEl.textContent = "—";
    }
  }

  function setLoading(isLoading) {
    if (!statusEl) {
      return;
    }
    statusEl.textContent = isLoading ? LOADING_MESSAGE : "";
    statusEl.classList.toggle("hidden", !isLoading);
    if (errorEl) {
      errorEl.classList.add("hidden");
      errorEl.textContent = "";
    }
    if (bodyEl) {
      bodyEl.classList.toggle("opacity-60", isLoading);
    }
  }

  function showError(message) {
    setLoading(false);
    if (errorEl) {
      errorEl.textContent = message || INSUFFICIENT_MESSAGE;
      errorEl.classList.remove("hidden");
    }
    if (latestPriceEl) {
      latestPriceEl.textContent = "—";
    }
    if (nextPriceEl) {
      nextPriceEl.textContent = "—";
    }
    if (latestDateEl) {
      latestDateEl.textContent = "—";
    }
    if (targetEl) {
      targetEl.textContent = "—";
    }
    if (unitEl) {
      unitEl.textContent = "—";
    }
    if (methodEl) {
      methodEl.textContent = "";
    }
    if (modelStatusEl) {
      modelStatusEl.textContent = "";
    }
    if (noteEl) {
      noteEl.textContent = "";
    }
    if (warningEl) {
      warningEl.textContent = "";
    }
    setPredictionUnavailable(message || ERROR_MESSAGE);
  }

  function updateContext() {
    if (seriesEl) {
      seriesEl.textContent = selectedSeries() || "—";
    }
    if (!locationEl) {
      return;
    }
    var location = locationSelect && locationSelect.value;
    locationEl.textContent = location || "—";
  }

  function render(payload) {
    setLoading(false);
    window.CropMandiLastEstimate = payload;
    if (errorEl) {
      errorEl.classList.add("hidden");
      errorEl.textContent = "";
    }
    if (latestPriceEl) {
      latestPriceEl.textContent = formatPrice(payload.latest_observed_price);
    }
    if (nextPriceEl) {
      nextPriceEl.textContent = formatPrice(payload.next_session_estimate);
    }
    if (latestDateEl) {
      latestDateEl.textContent = formatDate(payload.latest_observation_date);
    }
    if (targetEl) {
      if (payload.next_session_known && (payload.target_session || payload.next_session)) {
        targetEl.textContent = formatDate(payload.target_session || payload.next_session);
      } else {
        targetEl.textContent = "—";
      }
    }
    if (unitEl) {
      unitEl.textContent = unitLabel(payload.unit);
    }
    if (methodEl) {
      methodEl.textContent = "";
    }
    if (modelStatusEl) {
      modelStatusEl.textContent = "";
    }
    if (noteEl) {
      noteEl.textContent = "";
    }
    if (warningEl) {
      warningEl.textContent = "";
    }
    var recCrop = $("dash-rec-crop");
    var recVariety = $("dash-rec-variety");
    if (recCrop) {
      recCrop.textContent = commodity() === "pepper" ? "Black Pepper" : "Coffee";
    }
    if (recVariety) {
      recVariety.textContent = payload.series || selectedSeries() || "—";
    }
    updateContext();
  }

  function loadEstimate() {
    if (!window.CropMandiAPI || !CropMandiAPI.getNextSessionEstimate) {
      showError(ERROR_MESSAGE);
      return;
    }
    var series = selectedSeries();
    if (!series) {
      return;
    }
    var seq = ++requestSeq;
    updateContext();
    setLoading(true);
    CropMandiAPI.getNextSessionEstimate(commodity(), series)
      .then(function (payload) {
        if (seq !== requestSeq) {
          return;
        }
        if (!payload) {
          showError(ERROR_MESSAGE);
          return;
        }
        render(payload);
      })
      .catch(function (err) {
        if (seq !== requestSeq) {
          return;
        }
        if (err && (err.status === 404 || err.code === "no_available_observations")) {
          showError(INSUFFICIENT_MESSAGE);
          return;
        }
        showError(INSUFFICIENT_MESSAGE);
      });
  }

  function init() {
    cropSelect = $("dash-crop");
    seriesSelect = $("dash-series");
    locationSelect = $("dash-location");
    refreshButton = $("dash-refresh");
    statusEl = $("dash-est-status");
    errorEl = $("dash-est-error");
    bodyEl = $("dash-est-body");
    seriesEl = $("dash-est-series");
    locationEl = $("dash-est-location");
    latestPriceEl = $("dash-est-latest-price");
    nextPriceEl = $("dash-est-next-price");
    latestDateEl = $("dash-est-latest-date");
    targetEl = $("dash-est-target");
    unitEl = $("dash-est-unit");
    methodEl = $("dash-est-method");
    modelStatusEl = $("dash-est-model-status");
    noteEl = $("dash-est-note");
    warningEl = $("dash-est-warning");
    if (!cropSelect || !seriesSelect || !bodyEl) {
      return;
    }
    cropSelect.addEventListener("change", loadEstimate);
    seriesSelect.addEventListener("change", loadEstimate);
    if (locationSelect) {
      locationSelect.addEventListener("change", updateContext);
      if (window.MutationObserver) {
        new MutationObserver(updateContext).observe(locationSelect, {
          childList: true,
          subtree: true,
          attributes: true,
        });
      }
    }
    if (refreshButton) {
      refreshButton.addEventListener("click", loadEstimate);
    }
    loadEstimate();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

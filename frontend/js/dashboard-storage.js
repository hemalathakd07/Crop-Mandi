/**
 * Cold-storage lookup for the dashboard location selector.
 * Does not invent availability, crop compatibility, or facilities.
 */
(function () {
  "use strict";

  var ERROR_MESSAGE = "Unable to load cold-storage records. Please try again.";
  var cropSelect;
  var dashCropSelect;
  var locationSelect;
  var locationLabel;
  var headingEl;
  var quantityInput;
  var searchButton;
  var statusEl;
  var errorEl;
  var listEl;
  var countEl;
  var routingEl;
  var requestSeq = 0;

  function $(id) {
    return document.getElementById(id);
  }

  function selectedLocation() {
    if (locationSelect && locationSelect.value) {
      return locationSelect.value;
    }
    return "";
  }

  function setLoading(isLoading) {
    if (statusEl) {
      statusEl.textContent = isLoading ? "Searching nearby cold storages..." : "";
      statusEl.classList.toggle("hidden", !isLoading);
    }
    if (errorEl) {
      errorEl.classList.add("hidden");
      errorEl.textContent = "";
    }
    if (searchButton) {
      searchButton.disabled = isLoading;
    }
  }

  function showError(message) {
    setLoading(false);
    if (errorEl) {
      errorEl.textContent = message || ERROR_MESSAGE;
      errorEl.classList.remove("hidden");
    }
    if (listEl) {
      listEl.innerHTML = "";
    }
    if (countEl) {
      countEl.textContent = "";
    }
  }

  function capacityText(row) {
    if (row.capacity_mt === null || row.capacity_mt === undefined || row.capacity_mt === "") {
      return "Not available";
    }
    return row.capacity_mt + " MT";
  }

  function render(payload) {
    setLoading(false);
    var locationName = (payload && payload.requested_location) || selectedLocation() || "selected location";
    if (headingEl) {
      headingEl.textContent = "Cold Storage Near " + locationName;
    }
    if (locationLabel) {
      locationLabel.textContent = locationName;
    }
    var rows = (payload && payload.facilities) || [];
    if (countEl) {
      if (payload && payload.match_type === "NO_DATA") {
        countEl.textContent = "NO VERIFIED COLD STORAGE FOUND WITHIN 75 KM";
      } else if (payload && payload.match_type === "UNKNOWN_LOCATION") {
        countEl.textContent = "This location is not in the cold-storage catalog.";
      } else {
        countEl.textContent = rows.length ? "Cold Storage Near " + locationName : "NO VERIFIED COLD STORAGE FOUND WITHIN 75 KM";
      }
    }
    if (routingEl) {
      routingEl.textContent = rows.length
        ? "Distance is a straight-line estimate (Haversine)."
        : "";
    }
    if (!listEl) {
      return;
    }
    listEl.innerHTML = "";
    if (!rows.length) {
      var empty = document.createElement("li");
      empty.className = "text-on-surface-variant";
      empty.textContent = (payload && payload.message) || "NO VERIFIED COLD STORAGE FOUND WITHIN 75 KM";
      listEl.appendChild(empty);
      return;
    }
    rows.forEach(function (row) {
      var li = document.createElement("li");
      li.className = "border border-outline-variant/40 rounded-xl p-3 bg-white";

      var title = document.createElement("p");
      title.className = "text-sm font-semibold text-on-background";
      title.textContent = row.name || "Unnamed storage";
      li.appendChild(title);

      var placeBits = [];
      if (row.district) {
        placeBits.push(row.district);
      } else if (row.location) {
        placeBits.push(row.location);
      }
      if (row.distance_km !== null && row.distance_km !== undefined) {
        placeBits.push(row.distance_km + " km");
      }
      var place = document.createElement("p");
      place.className = "text-xs text-on-surface-variant mt-0.5";
      place.textContent = placeBits.join(" · ");
      li.appendChild(place);

      var facts = document.createElement("p");
      facts.className = "text-xs text-on-background mt-2";
      facts.textContent = "Capacity: " + capacityText(row);
      li.appendChild(facts);

      var source = document.createElement("p");
      source.className = "text-xs text-on-surface-variant mt-1";
      var sourceBits = ["Source: " + (row.source_name || row.source_label || row.source || "Unknown")];
      if (row.source_status) {
        sourceBits.push(row.source_status);
      }
      if (row.last_verified_at) {
        sourceBits.push(row.last_verified_at);
      }
      source.textContent = sourceBits.join(" · ");
      li.appendChild(source);

      if (row.address || row.phone || row.commodities_label) {
        var extra = document.createElement("p");
        extra.className = "text-xs text-on-surface-variant mt-1";
        extra.textContent = [row.address, row.phone ? "Phone: " + row.phone : "", row.commodities_label ? "Commodities: " + row.commodities_label : ""]
          .filter(Boolean)
          .join(" · ");
        li.appendChild(extra);
      }

      var actions = document.createElement("div");
      actions.className = "flex gap-3 mt-2";
      if (row.source_url) {
        var link = document.createElement("a");
        link.className = "text-xs font-semibold text-primary";
        link.href = row.source_url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "View Source";
        actions.appendChild(link);
      }
      if (row.directions_url) {
        var dir = document.createElement("a");
        dir.className = "text-xs font-semibold text-primary";
        dir.href = row.directions_url;
        dir.target = "_blank";
        dir.rel = "noopener noreferrer";
        dir.textContent = "Directions";
        actions.appendChild(dir);
      }
      if (actions.childNodes.length) {
        li.appendChild(actions);
      }
      listEl.appendChild(li);
    });
  }

  function search() {
    if (!window.CropMandiAPI || !CropMandiAPI.getColdStorageByLocation) {
      showError(ERROR_MESSAGE);
      return;
    }
    var location = selectedLocation();
    if (!location) {
      showError("Select a location first.");
      return;
    }
    var seq = ++requestSeq;
    setLoading(true);
    CropMandiAPI.getColdStorageByLocation(location, 5)
      .then(function (payload) {
        if (seq !== requestSeq) {
          return;
        }
        render(payload);
      })
      .catch(function () {
        if (seq !== requestSeq) {
          return;
        }
        showError(ERROR_MESSAGE);
      });
  }

  function init() {
    cropSelect = $("dash-storage-crop");
    dashCropSelect = $("dash-crop");
    locationSelect = $("dash-location");
    locationLabel = $("dash-storage-location-label");
    headingEl = $("dash-storage-heading");
    quantityInput = $("dash-storage-qty");
    searchButton = $("dash-storage-search");
    statusEl = $("dash-storage-status");
    errorEl = $("dash-storage-error");
    listEl = $("dash-storage-list");
    countEl = $("dash-storage-count");
    routingEl = $("dash-storage-routing");
    if (!searchButton || !listEl) {
      return;
    }
    if (dashCropSelect && cropSelect && !cropSelect.value) {
      cropSelect.value = dashCropSelect.value;
    }
    if (dashCropSelect && cropSelect) {
      dashCropSelect.addEventListener("change", function () {
        cropSelect.value = dashCropSelect.value;
      });
    }
    searchButton.addEventListener("click", function (event) {
      event.preventDefault();
      search();
    });
    if (locationSelect) {
      locationSelect.addEventListener("change", search);
      new MutationObserver(function () {
        if (locationSelect.value) {
          search();
        }
      }).observe(locationSelect, { childList: true, subtree: true });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

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
    rows.forEach(function (row, index) {
      var li = document.createElement("li");
      li.className = "bg-surface-container-low rounded-lg p-4 soft-inset";

      var title = document.createElement("p");
      title.className = "text-body-md font-body-md text-on-background font-semibold";
      title.textContent = index + 1 + ". " + (row.name || "Unnamed storage");
      li.appendChild(title);

      var badge = document.createElement("p");
      badge.className = "text-label-sm font-label-sm text-primary mt-1";
      if (row.match_type === "EXACT") {
        badge.textContent = "EXACT FACILITY";
      } else if (row.match_type === "DISTRICT_NEARBY") {
        badge.textContent = "DISTRICT NEARBY";
      } else {
        badge.textContent = "NEARBY FACILITY";
      }
      li.appendChild(badge);

      var loc = document.createElement("p");
      loc.className = "text-label-sm font-label-sm text-on-surface-variant mt-1";
      loc.textContent = "Location: " + (row.location || [row.district, row.state].filter(Boolean).join(", "));
      li.appendChild(loc);

      if (row.address) {
        var address = document.createElement("p");
        address.className = "text-body-md font-body-md text-on-surface-variant mt-1";
        address.textContent = row.address;
        li.appendChild(address);
      }

      var facts = document.createElement("p");
      facts.className = "text-label-sm font-label-sm text-on-background mt-3";
      var bits = [];
      if (row.distance_km !== null && row.distance_km !== undefined) {
        bits.push("Distance: " + row.distance_km + " km");
      }
      bits.push("Capacity: " + capacityText(row));
      facts.textContent = bits.join(" · ");
      li.appendChild(facts);

      var commodities = document.createElement("p");
      commodities.className = "text-label-sm font-label-sm text-on-surface-variant mt-1";
      commodities.textContent = "Commodity compatibility: " + (row.commodities_label || "Contact facility");
      li.appendChild(commodities);

      if (row.phone) {
        var phone = document.createElement("p");
        phone.className = "text-label-sm font-label-sm text-on-surface-variant mt-1";
        phone.textContent = "Phone: " + row.phone;
        li.appendChild(phone);
      }

      var availability = document.createElement("p");
      availability.className = "text-label-sm font-label-sm text-on-surface-variant mt-1";
      availability.textContent = "Availability: Contact facility";
      li.appendChild(availability);

      var source = document.createElement("p");
      source.className = "text-label-sm font-label-sm text-on-surface-variant mt-1";
      source.textContent = "Source: " + (row.source_name || row.source_label || row.source || "Unknown");
      li.appendChild(source);

      if (row.source_url) {
        var link = document.createElement("a");
        link.className = "text-label-sm font-label-sm text-primary mt-1 inline-block";
        link.href = row.source_url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "View source";
        li.appendChild(link);
      }

      var verified = document.createElement("p");
      verified.className = "text-label-sm font-label-sm text-on-surface-variant mt-1";
      verified.textContent = "Source status: " + (row.source_status || "NHB project record");
      li.appendChild(verified);

      if (row.last_verified_at) {
        var last = document.createElement("p");
        last.className = "text-label-sm font-label-sm text-on-surface-variant mt-1";
        last.textContent = "Last verified date: " + row.last_verified_at;
        li.appendChild(last);
      }

      if (row.directions_url) {
        var dir = document.createElement("a");
        dir.className = "text-label-sm font-label-sm text-primary mt-2 inline-block";
        dir.href = row.directions_url;
        dir.target = "_blank";
        dir.rel = "noopener noreferrer";
        dir.textContent = "Get Directions";
        li.appendChild(dir);
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

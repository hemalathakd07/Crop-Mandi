/**
 * Farm Calendar - month/year navigation, reminders, and views.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "cropmandi_farm_reminders";
  var MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];
  var TYPE_META = {
    sell: { label: "Best Sell Window", icon: "storefront", dayClass: "cal-day-sell", chipClass: "bg-primary text-on-primary", dotClass: "bg-primary" },
    harvest: { label: "Harvest Date", icon: "agriculture", dayClass: "cal-day-harvest", chipClass: "bg-tertiary text-on-tertiary", dotClass: "bg-tertiary" },
    weather: { label: "Weather Alert", icon: "warning", dayClass: "cal-day-alert", chipClass: "bg-error text-on-error", dotClass: "bg-error" },
    task: { label: "Task/Reminder", icon: "event_note", dayClass: "cal-day-task", chipClass: "border border-outline bg-surface-container-lowest text-on-surface-variant shadow-none", dotClass: "bg-outline" },
  };

  var view = "monthly";
  var year;
  var month;
  var selectedKey;
  var reminders = [];
  var editingId = null;

  var monthTitle;
  var yearInput;
  var grid;
  var monthlyView;
  var weeklyView;
  var upcomingView;
  var sidebarList;
  var modal;
  var modalTitle;
  var modalError;
  var titleInput;
  var dateInput;
  var typeSelect;
  var deleteButton;

  function $(id) {
    return document.getElementById(id);
  }

  function pad(n) {
    return String(n).padStart(2, "0");
  }

  function dateKey(y, m, d) {
    return y + "-" + pad(m + 1) + "-" + pad(d);
  }

  function todayKey() {
    var now = new Date();
    return dateKey(now.getFullYear(), now.getMonth(), now.getDate());
  }

  function parseKey(key) {
    var parts = String(key || "").split("-");
    return {
      y: Number(parts[0]),
      m: Number(parts[1]) - 1,
      d: Number(parts[2]),
    };
  }

  function daysInMonth(y, m) {
    return new Date(y, m + 1, 0).getDate();
  }

  function firstWeekday(y, m) {
    return new Date(y, m, 1).getDay();
  }

  function formatDisplayDate(key) {
    var p = parseKey(key);
    if (!p.y || p.m < 0) {
      return "";
    }
    return p.d + " " + MONTH_NAMES[p.m].slice(0, 3) + " " + p.y;
  }

  function typeMeta(type) {
    return TYPE_META[type] || TYPE_META.task;
  }

  function defaultReminders() {
    var now = new Date();
    var y = now.getFullYear();
    var m = now.getMonth();
    var last = daysInMonth(y, m);
    function keyFor(day) {
      return dateKey(y, m, Math.min(day, last));
    }
    return [
      { id: "seed-harvest", title: "Harvest Date", note: "", type: "harvest", date: keyFor(3) },
      { id: "seed-sell", title: "Best Sell Window", note: "", type: "sell", date: keyFor(10) },
      { id: "seed-fertilizer", title: "Apply fertilizer", note: "Coffee Plot A", type: "task", date: keyFor(14) },
      { id: "seed-rain", title: "Heavy Rain Expected", note: "Secure harvested crops", type: "weather", date: keyFor(15) },
      { id: "seed-mandi", title: "Check Mandi prices", note: "Black Pepper", type: "task", date: keyFor(19) },
    ];
  }

  function loadReminders() {
    try {
      var stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        var parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          reminders = parsed.filter(function (item) {
            return item && item.id && item.title && item.date && item.type;
          });
          return;
        }
      }
    } catch (err) {
      reminders = [];
    }
    reminders = defaultReminders();
    saveReminders();
  }

  function saveReminders() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(reminders));
  }

  function eventsOn(key) {
    return reminders.filter(function (item) {
      return item.date === key;
    });
  }

  function upcomingReminders() {
    var today = todayKey();
    return reminders
      .filter(function (item) {
        return item.date >= today;
      })
      .sort(function (a, b) {
        return a.date < b.date ? -1 : a.date > b.date ? 1 : 0;
      });
  }

  function weekRange() {
    var p = parseKey(selectedKey);
    var selected = new Date(p.y, p.m, p.d);
    var start = new Date(selected.getFullYear(), selected.getMonth(), selected.getDate() - selected.getDay());
    var end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 6);
    return { start: start, end: end };
  }

  function weekEvents() {
    var range = weekRange();
    var startKey = dateKey(range.start.getFullYear(), range.start.getMonth(), range.start.getDate());
    var endKey = dateKey(range.end.getFullYear(), range.end.getMonth(), range.end.getDate());
    return reminders
      .filter(function (item) {
        return item.date >= startKey && item.date <= endKey;
      })
      .sort(function (a, b) {
        return a.date < b.date ? -1 : a.date > b.date ? 1 : 0;
      });
  }

  function setView(next) {
    view = next;
    ["monthly", "weekly", "upcoming"].forEach(function (name) {
      var tab = $("cal-tab-" + name);
      if (tab) {
        tab.classList.toggle("cal-tab-active", name === view);
      }
    });
    if (monthlyView) {
      monthlyView.classList.toggle("hidden", view !== "monthly");
    }
    if (weeklyView) {
      weeklyView.classList.toggle("hidden", view !== "weekly");
    }
    if (upcomingView) {
      upcomingView.classList.toggle("hidden", view !== "upcoming");
    }
    render();
  }

  function shiftPeriod(delta) {
    if (view === "weekly") {
      var p = parseKey(selectedKey);
      var next = new Date(p.y, p.m, p.d + delta * 7);
      year = next.getFullYear();
      month = next.getMonth();
      selectedKey = dateKey(year, month, next.getDate());
    } else {
      month += delta;
      if (month > 11) {
        month = 0;
        year += 1;
      } else if (month < 0) {
        month = 11;
        year -= 1;
      }
      var last = daysInMonth(year, month);
      var sel = parseKey(selectedKey);
      selectedKey = dateKey(year, month, Math.min(sel.d || 1, last));
    }
    render();
  }

  function reminderCard(item, opts) {
    var meta = typeMeta(item.type);
    var card = document.createElement("div");
    card.className = "reminder-card group" + (item.type === "weather" ? " reminder-card-alert" : "");
    var note = item.note ? item.note + " • " : "";
    card.innerHTML =
      '<div class="reminder-icon' + (item.type === "weather" ? " reminder-icon-alert" : "") + '">' +
        '<span class="material-symbols-outlined text-[20px]">' + meta.icon + "</span>" +
      "</div>" +
      "<div>" +
        '<h5 class="font-data-tabular text-data-tabular text-on-background' + (item.type === "weather" ? " text-error font-bold" : "") + '">' + item.title + "</h5>" +
        '<p class="font-body-md text-body-md text-on-surface-variant text-sm mt-0.5">' + note + formatDisplayDate(item.date) + "</p>" +
      "</div>" +
      (opts && opts.showComplete
        ? '<button class="ml-auto text-outline hover:text-primary cal-complete-btn" type="button" data-id="' + item.id + '"><span class="material-symbols-outlined text-[20px]">check_circle</span></button>'
        : "");
    card.addEventListener("click", function (event) {
      if (event.target.closest(".cal-complete-btn")) {
        return;
      }
      openModal(item);
    });
    var complete = card.querySelector(".cal-complete-btn");
    if (complete) {
      complete.addEventListener("click", function (event) {
        event.stopPropagation();
        reminders = reminders.filter(function (row) {
          return row.id !== item.id;
        });
        saveReminders();
        render();
      });
    }
    return card;
  }

  function renderMonthHeader() {
    if (monthTitle) {
      if (view === "weekly") {
        var range = weekRange();
        monthTitle.textContent =
          formatDisplayDate(dateKey(range.start.getFullYear(), range.start.getMonth(), range.start.getDate())) +
          " – " +
          formatDisplayDate(dateKey(range.end.getFullYear(), range.end.getMonth(), range.end.getDate()));
      } else if (view === "upcoming") {
        monthTitle.textContent = "Upcoming";
      } else {
        monthTitle.textContent = MONTH_NAMES[month] + " " + year;
      }
    }
    if (yearInput && document.activeElement !== yearInput) {
      yearInput.value = String(year);
    }
  }

  function renderGrid() {
    if (!grid) {
      return;
    }
    grid.innerHTML = "";
    var blanks = firstWeekday(year, month);
    var total = daysInMonth(year, month);
    var today = todayKey();
    var i;
    for (i = 0; i < blanks; i += 1) {
      var empty = document.createElement("div");
      empty.className = "cal-day-empty";
      grid.appendChild(empty);
    }
    for (i = 1; i <= total; i += 1) {
      var key = dateKey(year, month, i);
      var items = eventsOn(key);
      var day = document.createElement("div");
      var dayClass = "cal-day";
      if (items.length) {
        dayClass += " " + typeMeta(items[0].type).dayClass;
      }
      if (key === today) {
        dayClass += " cal-day-today";
      }
      if (key === selectedKey) {
        dayClass += " cal-day-selected";
      }
      day.className = dayClass;
      day.setAttribute("data-date", key);
      (function (dayKey) {
        var chips = "";
        items.slice(0, 2).forEach(function (item) {
          var meta = typeMeta(item.type);
          chips +=
            '<button type="button" class="cal-chip ' + meta.chipClass + '" data-id="' + item.id + '">' +
            item.title +
            "</button>";
        });
        if (items.length > 2) {
          chips += '<span class="cal-chip border border-outline text-on-surface-variant shadow-none">+' + (items.length - 2) + "</span>";
        }
        var dots = items
          .slice(0, 3)
          .map(function (item) {
            return '<div class="cal-dot ' + typeMeta(item.type).dotClass + '"></div>';
          })
          .join("");

        day.innerHTML =
          '<span class="cal-day-num">' + i + "</span>" +
          '<div class="cal-chip-wrap">' + chips + "</div>" +
          '<div class="cal-dots">' + dots + "</div>";

        day.addEventListener("click", function (event) {
          var chip = event.target.closest("[data-id]");
          selectedKey = dayKey;
          if (chip && chip.getAttribute("data-id")) {
            var found = reminders.find(function (row) {
              return row.id === chip.getAttribute("data-id");
            });
            if (found) {
              openModal(found);
              return;
            }
          }
          render();
        });
        day.addEventListener("dblclick", function () {
          selectedKey = dayKey;
          openModal(null, dayKey);
        });
      })(key);
      grid.appendChild(day);
    }
  }

  function renderList(container, items, emptyText, opts) {
    if (!container) {
      return;
    }
    container.innerHTML = "";
    if (!items.length) {
      var empty = document.createElement("p");
      empty.className = "cal-empty";
      empty.textContent = emptyText;
      container.appendChild(empty);
      return;
    }
    items.forEach(function (item) {
      container.appendChild(reminderCard(item, opts));
    });
  }

  function render() {
    renderMonthHeader();
    renderGrid();
    renderList(weeklyView, weekEvents(), "No events in this week.", { showComplete: true });
    var upcoming = upcomingReminders();
    renderList(upcomingView, upcoming, "No upcoming reminders.", { showComplete: true });
    renderList(sidebarList, upcoming.slice(0, 6), "No upcoming reminders.", { showComplete: true });
  }

  function showModalError(message) {
    if (!modalError) {
      return;
    }
    modalError.textContent = message || "";
    modalError.classList.toggle("hidden", !message);
  }

  function openModal(item, dateOverride) {
    editingId = item ? item.id : null;
    if (modalTitle) {
      modalTitle.textContent = item ? "Edit Reminder" : "Add Reminder";
    }
    if (titleInput) {
      titleInput.value = item ? item.title : "";
    }
    if (dateInput) {
      dateInput.value = item ? item.date : dateOverride || selectedKey || todayKey();
    }
    if (typeSelect) {
      typeSelect.value = item ? item.type : "task";
    }
    if (deleteButton) {
      deleteButton.classList.toggle("hidden", !item);
    }
    showModalError("");
    if (modal) {
      modal.classList.remove("hidden");
      modal.setAttribute("aria-hidden", "false");
    }
    if (titleInput) {
      titleInput.focus();
    }
  }

  function closeModal() {
    editingId = null;
    if (modal) {
      modal.classList.add("hidden");
      modal.setAttribute("aria-hidden", "true");
    }
  }

  function saveFromModal() {
    var title = titleInput ? String(titleInput.value || "").trim() : "";
    var date = dateInput ? dateInput.value : "";
    var type = typeSelect ? typeSelect.value : "task";
    if (!title) {
      showModalError("Please enter a title.");
      return;
    }
    if (!date) {
      showModalError("Please choose a date.");
      return;
    }
    if (!TYPE_META[type]) {
      type = "task";
    }
    if (editingId) {
      reminders = reminders.map(function (item) {
        if (item.id !== editingId) {
          return item;
        }
        return { id: item.id, title: title, note: item.note || "", type: type, date: date };
      });
    } else {
      reminders.push({
        id: String(Date.now()),
        title: title,
        note: "",
        type: type,
        date: date,
      });
    }
    saveReminders();
    var parsed = parseKey(date);
    year = parsed.y;
    month = parsed.m;
    selectedKey = date;
    closeModal();
    render();
  }

  function deleteFromModal() {
    if (!editingId) {
      return;
    }
    reminders = reminders.filter(function (item) {
      return item.id !== editingId;
    });
    saveReminders();
    closeModal();
    render();
  }

  function init() {
    var now = new Date();
    year = now.getFullYear();
    month = now.getMonth();
    selectedKey = todayKey();

    monthTitle = $("cal-month-title");
    yearInput = $("cal-year-input");
    grid = $("cal-grid");
    monthlyView = $("cal-monthly-view");
    weeklyView = $("cal-weekly-view");
    upcomingView = $("cal-upcoming-view");
    sidebarList = $("cal-sidebar-list");
    modal = $("cal-modal");
    modalTitle = $("cal-modal-title");
    modalError = $("cal-modal-error");
    titleInput = $("cal-reminder-title");
    dateInput = $("cal-reminder-date");
    typeSelect = $("cal-reminder-type");
    deleteButton = $("cal-modal-delete");

    if (!grid || !monthTitle) {
      return;
    }

    loadReminders();

    $("cal-tab-monthly") && $("cal-tab-monthly").addEventListener("click", function () { setView("monthly"); });
    $("cal-tab-weekly") && $("cal-tab-weekly").addEventListener("click", function () { setView("weekly"); });
    $("cal-tab-upcoming") && $("cal-tab-upcoming").addEventListener("click", function () { setView("upcoming"); });
    $("cal-prev") && $("cal-prev").addEventListener("click", function () { shiftPeriod(-1); });
    $("cal-next") && $("cal-next").addEventListener("click", function () { shiftPeriod(1); });
    $("cal-add-button") && $("cal-add-button").addEventListener("click", function () { openModal(null); });
    $("cal-view-all") && $("cal-view-all").addEventListener("click", function () { setView("upcoming"); });
    $("cal-modal-close") && $("cal-modal-close").addEventListener("click", closeModal);
    $("cal-modal-cancel") && $("cal-modal-cancel").addEventListener("click", closeModal);
    $("cal-modal-save") && $("cal-modal-save").addEventListener("click", saveFromModal);
    deleteButton && deleteButton.addEventListener("click", deleteFromModal);

    if (yearInput) {
      yearInput.addEventListener("change", function () {
        var nextYear = Number(yearInput.value);
        if (!Number.isFinite(nextYear)) {
          yearInput.value = String(year);
          return;
        }
        year = Math.trunc(nextYear);
        var last = daysInMonth(year, month);
        var sel = parseKey(selectedKey);
        selectedKey = dateKey(year, month, Math.min(sel.d || 1, last));
        render();
      });
    }

    if (modal) {
      modal.addEventListener("click", function (event) {
        if (event.target === modal) {
          closeModal();
        }
      });
    }

    render();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

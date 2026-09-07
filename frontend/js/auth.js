/**
 * Browser-side farmer auth for Login / Register / Access Dashboard.
 * Session is stored locally; payment demo identity is unchanged.
 */
(function (global) {
  "use strict";

  var USERS_KEY = "cropmandi_auth_users";
  var SESSION_KEY = "cropmandi_auth_session";
  var DASHBOARD_HREF = "../cropmandi_ai_dashboard/code.html";
  var DEFAULT_NAME = "Hemalatha";

  function readUsers() {
    try {
      var raw = localStorage.getItem(USERS_KEY);
      var list = raw ? JSON.parse(raw) : [];
      return Array.isArray(list) ? list : [];
    } catch (err) {
      return [];
    }
  }

  function writeUsers(users) {
    localStorage.setItem(USERS_KEY, JSON.stringify(users));
  }

  function normalize(value) {
    return String(value || "").trim().toLowerCase();
  }

  function matchesIdentifier(user, identifier) {
    var needle = normalize(identifier);
    if (!needle) {
      return false;
    }
    return (
      normalize(user.phone) === needle ||
      normalize(user.email) === needle ||
      normalize(user.identifier) === needle
    );
  }

  function getSession() {
    try {
      var raw = localStorage.getItem(SESSION_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (err) {
      return null;
    }
  }

  function setSession(user) {
    var session = {
      name: user.name || DEFAULT_NAME,
      phone: user.phone || "",
      email: user.email || "",
      location: user.location || "",
      crop: user.crop || "",
    };
    localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    if (session.location) {
      localStorage.setItem("cropmandi_dash_location", session.location);
    }
    return session;
  }

  function displayName() {
    var session = getSession();
    if (session && session.name) {
      return String(session.name).trim();
    }
    return DEFAULT_NAME;
  }

  function firstName() {
    return displayName().split(/\s+/)[0] || DEFAULT_NAME;
  }

  function goDashboard() {
    window.location.href = DASHBOARD_HREF;
  }

  function showAuthMessage(text, isError) {
    var el = document.getElementById("auth-message");
    if (!el) {
      return;
    }
    el.textContent = text || "";
    el.classList.toggle("hidden", !text);
    el.classList.toggle("text-error", !!isError);
    el.classList.toggle("text-primary", !isError);
  }

  function registerUser(fields) {
    var name = String(fields.name || "").trim();
    var phone = String(fields.phone || "").trim();
    var email = String(fields.email || "").trim();
    var password = String(fields.password || "");
    var location = String(fields.location || "").trim();
    var crop = String(fields.crop || "").trim();
    if (!name) {
      return { ok: false, message: "Please enter your full name." };
    }
    if (!phone && !email) {
      return { ok: false, message: "Please enter a mobile number or email." };
    }
    if (!password || password.length < 4) {
      return { ok: false, message: "Please choose a password with at least 4 characters." };
    }
    var users = readUsers();
    var identifier = phone || email;
    var exists = users.some(function (user) {
      return matchesIdentifier(user, identifier) || (email && matchesIdentifier(user, email));
    });
    if (exists) {
      return { ok: false, message: "An account with this phone or email already exists. Please log in." };
    }
    var user = {
      name: name,
      phone: phone,
      email: email,
      identifier: identifier,
      password: password,
      location: location,
      crop: crop,
    };
    users.push(user);
    writeUsers(users);
    setSession(user);
    return { ok: true, user: user };
  }

  function loginUser(identifier, password) {
    var id = String(identifier || "").trim();
    var pass = String(password || "");
    if (!id || !pass) {
      return { ok: false, message: "Please enter your phone/email and password." };
    }
    var users = readUsers();
    var user = null;
    users.forEach(function (row) {
      if (matchesIdentifier(row, id) && String(row.password) === pass) {
        user = row;
      }
    });
    if (!user) {
      return { ok: false, message: "Incorrect phone/email or password." };
    }
    setSession(user);
    return { ok: true, user: user };
  }

  function bindAuthPage() {
    var loginForm = document.getElementById("form-login");
    var registerForm = document.getElementById("form-register");
    if (loginForm) {
      loginForm.addEventListener("submit", function (event) {
        event.preventDefault();
        var identifier = (document.getElementById("login-identifier") || {}).value;
        var password = (document.getElementById("login-password") || {}).value;
        if (!String(identifier || "").trim() && !String(password || "") && getSession()) {
          goDashboard();
          return;
        }
        var result = loginUser(identifier, password);
        if (!result.ok) {
          showAuthMessage(result.message, true);
          return;
        }
        goDashboard();
      });
    }
    var accessBtn = document.getElementById("btn-access-dashboard");
    if (accessBtn && loginForm) {
      accessBtn.addEventListener("click", function (event) {
        event.preventDefault();
        if (typeof loginForm.requestSubmit === "function") {
          loginForm.requestSubmit();
        } else {
          loginForm.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
        }
      });
    }
    if (registerForm) {
      registerForm.addEventListener("submit", function (event) {
        event.preventDefault();
        var result = registerUser({
          name: (document.getElementById("reg-name") || {}).value,
          location: (document.getElementById("reg-location") || {}).value,
          crop: (document.getElementById("reg-crop") || {}).value,
          phone: (document.getElementById("reg-phone") || {}).value,
          email: (document.getElementById("reg-email") || {}).value,
          password: (document.getElementById("reg-password") || {}).value,
        });
        if (!result.ok) {
          showAuthMessage(result.message, true);
          return;
        }
        goDashboard();
      });
    }
  }

  global.CropMandiAuth = {
    getSession: getSession,
    displayName: displayName,
    firstName: firstName,
    bindAuthPage: bindAuthPage,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindAuthPage);
  } else {
    bindAuthPage();
  }
})(window);

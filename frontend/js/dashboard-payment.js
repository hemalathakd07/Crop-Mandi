/**
 * Razorpay TEST checkout — server-priced ₹100 demo.
 * Checkout opens in the Pay click handler after the backend creates an order.
 */
(function () {
  "use strict";

  var DEMO_AMOUNT_INR = 100;
  var CHECKOUT_SCRIPT = "https://checkout.razorpay.com/v1/checkout.js";
  var paying = false;

  function api() {
    return window.CropMandiAPI;
  }

  function el(id) {
    return document.getElementById(id);
  }

  function userMessage(err) {
    var code = err && err.code;
    var status = err && err.status;
    if (code === "invalid_signature" || code === "invalid_order") {
      return "Payment verification failed.";
    }
    if (code === "invalid_amount" || code === "invalid_currency" || code === "invalid_crop") {
      return "Unable to create payment order.";
    }
    if (code === "razorpay_order_failed" || code === "payments_not_configured") {
      return "Unable to create payment order.";
    }
    if (code === "payment_failed") {
      return "Payment failed. Please try again.";
    }
    if (status === 0 || (err && err.name === "TypeError")) {
      return "Something went wrong. Please try again.";
    }
    return (err && err.message) || "Something went wrong. Please try again.";
  }

  function setStatus(text) {
    var s = el("dash-pay-status");
    var e = el("dash-pay-error");
    var ok = el("dash-pay-success");
    if (s) {
      s.textContent = text || "";
      s.classList.toggle("hidden", !text);
    }
    if (e) {
      e.textContent = "";
      e.classList.add("hidden");
    }
    if (ok) {
      ok.textContent = "";
      ok.classList.add("hidden");
    }
  }

  function setBusy(busy) {
    var btn = el("dash-pay-button");
    paying = !!busy;
    if (!btn) {
      return;
    }
    btn.disabled = !!busy;
    btn.textContent = busy ? "Processing…" : "Pay ₹100 (Test Mode)";
  }

  function setError(text) {
    var s = el("dash-pay-status");
    var e = el("dash-pay-error");
    var ok = el("dash-pay-success");
    if (s) {
      s.textContent = "";
      s.classList.add("hidden");
    }
    if (ok) {
      ok.textContent = "";
      ok.classList.add("hidden");
    }
    if (e) {
      e.textContent = text || "Payment failed. Please try again.";
      e.classList.remove("hidden");
    }
    setBusy(false);
  }

  function setSuccess(text) {
    var s = el("dash-pay-status");
    var e = el("dash-pay-error");
    var ok = el("dash-pay-success");
    if (s) {
      s.textContent = "";
      s.classList.add("hidden");
    }
    if (e) {
      e.textContent = "";
      e.classList.add("hidden");
    }
    if (ok) {
      ok.textContent = text || "";
      ok.classList.toggle("hidden", !text);
    }
    setBusy(false);
  }

  function cropQty() {
    var cropEl = el("dash-storage-crop");
    var qtyEl = el("dash-storage-qty");
    var crop = cropEl && cropEl.value ? cropEl.value : "coffee";
    var raw = qtyEl ? String(qtyEl.value || "").trim() : "";
    var qty = Number(raw);
    if (!raw || !Number.isFinite(qty) || qty <= 0) {
      qty = 10;
    }
    return { crop: crop, quantity: qty };
  }

  function loadCheckoutScript() {
    return new Promise(function (resolve, reject) {
      if (typeof window.Razorpay === "function") {
        resolve();
        return;
      }
      if (window.__razorpayScriptFailed) {
        reject(new Error("Unable to load payment checkout. Please try again."));
        return;
      }
      var existing = document.querySelector('script[src="' + CHECKOUT_SCRIPT + '"]');
      if (existing) {
        existing.addEventListener("load", function () {
          if (typeof window.Razorpay === "function") {
            resolve();
          } else {
            reject(new Error("Unable to load payment checkout. Please try again."));
          }
        });
        existing.addEventListener("error", function () {
          reject(new Error("Unable to load payment checkout. Please try again."));
        });
        return;
      }
      var script = document.createElement("script");
      script.src = CHECKOUT_SCRIPT;
      script.async = true;
      script.onload = function () {
        if (typeof window.Razorpay === "function") {
          resolve();
        } else {
          reject(new Error("Unable to load payment checkout. Please try again."));
        }
      };
      script.onerror = function () {
        window.__razorpayScriptFailed = true;
        reject(new Error("Unable to load payment checkout. Please try again."));
      };
      document.head.appendChild(script);
    });
  }

  function verifyOrder(order, rzpResponse) {
    var client = api();
    if (!client) {
      setError("Something went wrong. Please try again.");
      return;
    }
    setStatus("Verifying payment...");
    return client
      .verifyPayment({
        razorpay_order_id: order.order_id,
        razorpay_payment_id: rzpResponse.razorpay_payment_id,
        razorpay_signature: rzpResponse.razorpay_signature,
      })
      .then(function (body) {
        if (!body || body.verified !== true) {
          throw new Error("Payment verification failed.");
        }
        var status = body.payment && body.payment.status;
        if (status !== "CAPTURED" && status !== "AUTHORIZED") {
          throw new Error("Payment verification failed.");
        }
        setSuccess(
          "Payment successful. Crop: " +
            order.crop +
            ". Quantity: " +
            order.quantity +
            " kg. Amount: ₹" +
            DEMO_AMOUNT_INR +
            ". Status: " +
            status +
            "."
        );
      })
      .catch(function (err) {
        setError(userMessage(err) === (err && err.message) ? "Payment verification failed." : userMessage(err));
      });
  }

  async function onPayClick(event) {
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }
    if (paying) {
      return;
    }
    var client = api();
    if (!client) {
      setError("Something went wrong. Please try again.");
      return;
    }
    try {
      setBusy(true);
      await loadCheckoutScript();
      if (typeof window.Razorpay !== "function") {
        throw new Error("Unable to load payment checkout. Please try again.");
      }
      var sel = cropQty();
      setStatus("Creating payment order...");
      var data = await client.createPaymentOrder({
        crop: sel.crop,
        quantity: sel.quantity,
        amount: DEMO_AMOUNT_INR,
        currency: "INR",
        listing_id: "",
      });
      var keyId = String((data && data.key_id) || "").trim();
      var orderId = String((data && data.order_id) || "").trim();
      var amount = Number(data && data.amount);
      var currency = String((data && data.currency) || "INR").trim();
      if (!keyId || !orderId || !Number.isFinite(amount) || amount <= 0 || !currency) {
        throw Object.assign(new Error("Unable to create payment order."), {
          code: "razorpay_order_failed",
        });
      }
      var order = {
        key_id: keyId,
        order_id: orderId,
        amount: amount,
        currency: currency,
        crop: sel.crop,
        quantity: sel.quantity,
      };
      setStatus("Opening checkout...");
      var checkout = new window.Razorpay({
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        order_id: order.order_id,
        name: "CropMandi AI",
        description: "Razorpay TEST demo — not a real sale or booking",
        prefill: {},
        theme: { color: "#004532" },
        handler: function (rzpResponse) {
          verifyOrder(order, rzpResponse);
        },
        modal: {
          ondismiss: function () {
            client.cancelPayment(order.order_id).catch(function () {});
            setBusy(false);
            setStatus("Payment cancelled.");
          },
        },
      });
      if (checkout && typeof checkout.on === "function") {
        checkout.on("payment.failed", function () {
          setError("Payment failed. Please try again.");
        });
      }
      checkout.open();
    } catch (err) {
      setError(userMessage(err));
    }
  }

  function bindPayButton() {
    var btn = el("dash-pay-button");
    if (!btn) {
      return false;
    }
    if (btn.getAttribute("data-cropmandi-pay-bound") === "1") {
      return true;
    }
    btn.removeAttribute("onclick");
    btn.onclick = null;
    btn.addEventListener("click", onPayClick);
    btn.setAttribute("data-cropmandi-pay-bound", "1");
    return true;
  }

  function start() {
    bindPayButton();
  }

  start();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  }
})();

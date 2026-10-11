// Invite page helper (same-origin; replaces the CSP-blocked inline onclick).
// Selects the shareable link text on focus so the inviter can copy it.
document.addEventListener("DOMContentLoaded", function () {
  var el = document.getElementById("signup-url");
  if (el) {
    el.addEventListener("focus", function () {
      el.select();
    });
  }
});

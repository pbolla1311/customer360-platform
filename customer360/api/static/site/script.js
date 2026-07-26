(function () {
  "use strict";

  var dot = document.getElementById("status-dot");
  var text = document.getElementById("status-text");

  if (!dot || !text) {
    return;
  }

  fetch("/health", { cache: "no-store" })
    .then(function (response) {
      if (!response.ok) {
        throw new Error("Unexpected status: " + response.status);
      }
      return response.json();
    })
    .then(function (data) {
      dot.classList.add("status-dot--ok");
      var version = data && data.version ? " · v" + data.version : "";
      text.textContent = "API operational" + version;
    })
    .catch(function () {
      dot.classList.add("status-dot--down");
      text.textContent = "API status unavailable";
    });
})();

(function () {
  "use strict";

  var REPO = "pbolla1311/customer360-platform";
  var API_BASE = "https://api.github.com/repos/" + REPO;
  var CACHE_KEY = "c360:github-stats:v1";
  var CACHE_TTL_MS = 60 * 60 * 1000; // 1 hour: keeps well under the 60/hr
  // unauthenticated GitHub API rate limit even across repeat visits.

  var els = {
    stars: document.getElementById("stat-stars"),
    forks: document.getElementById("stat-forks"),
    license: document.getElementById("stat-license"),
    release: document.getElementById("stat-release"),
  };

  if (!els.stars || !els.forks || !els.license || !els.release) {
    return;
  }

  function render(data) {
    // "Not released" is only ever set explicitly, when the releases API
    // confirms (via 404) that the repository has no releases yet -- an
    // unreachable/failed lookup renders "—" (unknown), same as the other
    // fields, rather than falsely asserting "Not released".
    els.stars.textContent = typeof data.stars === "number" ? String(data.stars) : "—";
    els.forks.textContent = typeof data.forks === "number" ? String(data.forks) : "—";
    els.license.textContent = data.license || "—";
    els.release.textContent = data.release || "—";
  }

  function readCache() {
    try {
      var raw = window.localStorage.getItem(CACHE_KEY);
      if (!raw) {
        return null;
      }
      var parsed = JSON.parse(raw);
      if (!parsed || typeof parsed.savedAt !== "number" || !parsed.data) {
        return null;
      }
      if (Date.now() - parsed.savedAt > CACHE_TTL_MS) {
        return null;
      }
      return parsed.data;
    } catch (err) {
      return null;
    }
  }

  function writeCache(data) {
    try {
      window.localStorage.setItem(
        CACHE_KEY,
        JSON.stringify({ savedAt: Date.now(), data: data })
      );
    } catch (err) {
      // Storage unavailable (private browsing, quota, disabled) -- the
      // widget still works, it just re-fetches on the next page load.
    }
  }

  function fetchJson(url) {
    return fetch(url, { headers: { Accept: "application/vnd.github+json" } })
      .then(function (response) {
        if (response.status === 404) {
          return { __notFound: true };
        }
        if (!response.ok) {
          return null;
        }
        return response.json();
      })
      .catch(function () {
        return null;
      });
  }

  var cached = readCache();
  if (cached) {
    render(cached);
    return;
  }

  render({});

  Promise.all([fetchJson(API_BASE), fetchJson(API_BASE + "/releases/latest")]).then(
    function (results) {
      var repo = results[0];
      var release = results[1];

      var license = null;
      if (repo && repo.license) {
        var spdxId = repo.license.spdx_id;
        license = spdxId && spdxId !== "NOASSERTION" ? spdxId : repo.license.name || null;
      }

      var releaseTag = null;
      if (release && !release.__notFound && release.tag_name) {
        releaseTag = release.tag_name;
      }

      var data = {
        stars: repo && typeof repo.stargazers_count === "number" ? repo.stargazers_count : null,
        forks: repo && typeof repo.forks_count === "number" ? repo.forks_count : null,
        license: license,
        release: release && release.__notFound ? "Not released" : releaseTag,
      };

      render(data);

      // Only cache a response backed by a real repo lookup -- avoids
      // caching a rate-limited/errored "—" state for the full TTL.
      if (repo) {
        writeCache(data);
      }
    }
  );
})();

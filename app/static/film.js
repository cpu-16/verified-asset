(function () {
  var form = document.querySelector("form.film");
  if (!form) return;
  var input = form.querySelector('input[type="file"]');
  var status = form.querySelector(".film-status");
  var frames = form.querySelector(".film-frames");
  var unreadable = "This browser can't read that video. Film it here with your phone's camera, or take photos instead.";
  var network = "The upload didn't go through. Check the connection and try again.";

  form.addEventListener("submit", function (e) { e.preventDefault(); });

  function metadata(video, url) {
    return new Promise(function (resolve, reject) {
      var timer = setTimeout(failed, 15000);
      function done(error) {
        clearTimeout(timer);
        video.removeEventListener("loadedmetadata", loaded);
        video.removeEventListener("error", failed);
        if (error) reject(new Error(unreadable));
        else resolve();
      }
      function loaded() { done(false); }
      function failed() { done(true); }
      video.addEventListener("loadedmetadata", loaded);
      video.addEventListener("error", failed);
      video.src = url;
      video.load();
    });
  }

  function seek(video, time) {
    return new Promise(function (resolve, reject) {
      var callback, delay, didSeek = false, didPaint = false;
      var timer = setTimeout(failed, 4000);
      function done(error) {
        clearTimeout(timer);
        clearTimeout(delay);
        if (callback !== undefined) video.cancelVideoFrameCallback(callback);
        video.removeEventListener("seeked", sought);
        video.removeEventListener("error", failed);
        if (error) reject(new Error(unreadable));
        else resolve();
      }
      function failed() { done(true); }
      function sought() {
        didSeek = true;
        if (video.requestVideoFrameCallback) {
          if (didPaint) done(false);
        } else {
          delay = setTimeout(function () { done(false); }, 60);
        }
      }
      video.addEventListener("seeked", sought);
      video.addEventListener("error", failed);
      // Register before seeking: a paused video's frame callback can precede seeked.
      if (video.requestVideoFrameCallback) {
        callback = video.requestVideoFrameCallback(function () {
          didPaint = true;
          if (didSeek) done(false);
        });
      }
      try { video.currentTime = time; } catch (error) { failed(); }
    });
  }

  function sharpness(canvas, small) {
    var width = small.width, height = small.height;
    var ctx = small.getContext("2d");
    ctx.drawImage(canvas, 0, 0, width, height);
    var pixels = ctx.getImageData(0, 0, width, height).data;
    var gray = new Float32Array(width * height);
    for (var i = 0; i < gray.length; i++) {
      gray[i] = pixels[i * 4] * 0.299 + pixels[i * 4 + 1] * 0.587 + pixels[i * 4 + 2] * 0.114;
    }
    var sum = 0, squares = 0, count = 0;
    for (var y = 1; y < height - 1; y++) {
      for (var x = 1; x < width - 1; x++) {
        var p = y * width + x;
        var value = gray[p - width] + gray[p + width] + gray[p - 1] + gray[p + 1] - 4 * gray[p];
        sum += value;
        squares += value * value;
        count++;
      }
    }
    return count ? Math.max(0, squares / count - Math.pow(sum / count, 2)) : 0;
  }

  function jpeg(canvas) {
    return new Promise(function (resolve, reject) {
      canvas.toBlob(function (blob) {
        if (blob) resolve(blob);
        else reject(new Error("Couldn't read a frame. Try filming again, or take photos instead."));
      }, "image/jpeg", 0.85);
    });
  }

  input.addEventListener("change", async function () {
    var file = input.files && input.files[0];
    if (!file || form.classList.contains("busy")) return;
    form.classList.add("busy");
    form.classList.remove("bad");
    input.disabled = true;
    frames.textContent = "";
    status.textContent = "Reading your video: 0 of 10";
    var video = document.createElement("video");
    var urls = [];
    video.setAttribute("muted", "");
    video.setAttribute("playsinline", "");
    video.setAttribute("preload", "auto");
    video.muted = true;
    video.playsInline = true;
    video.preload = "auto";
    video.style.cssText = "position:fixed;left:-10000px;top:0;width:1px;height:1px;pointer-events:none";
    video.setAttribute("aria-hidden", "true");
    document.body.appendChild(video);
    try {
      urls.push(URL.createObjectURL(file));
      await metadata(video, urls[0]);
      var duration = video.duration;
      if (!isFinite(duration)) throw new Error(unreadable);
      if (duration < 3) throw new Error("That clip is too short. Film for 10 to 30 seconds.");
      if (duration > 120) throw new Error("That clip is longer than 2 minutes. Film for 10 to 30 seconds.");
      if (!video.videoWidth || !video.videoHeight) throw new Error(unreadable);

      // Safari needs playback to start once before it will paint sought frames.
      var playTimer;
      try {
        await Promise.race([
          video.play(),
          new Promise(function (resolve) { playTimer = setTimeout(resolve, 4000); })
        ]);
      } catch (error) {
      } finally {
        clearTimeout(playTimer);
        video.pause();
      }

      var scale = Math.min(1, 1280 / Math.max(video.videoWidth, video.videoHeight));
      var canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
      canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
      var best = document.createElement("canvas");
      best.width = canvas.width;
      best.height = canvas.height;
      var small = document.createElement("canvas");
      small.width = Math.min(160, canvas.width);
      small.height = Math.max(3, Math.round(canvas.height * small.width / canvas.width));
      var data = new FormData(), times = [];
      for (var i = 0; i < 10; i++) {
        var instant = duration * (0.04 + 0.92 * i / 9);
        var bestScore = -1, bestTime;
        // Pick the sharper nearby sample to avoid a moment of hand movement.
        for (var j = 0; j < 2; j++) {
          var time = Math.max(0, Math.min(duration, instant + (j ? 0.2 : -0.2)));
          await seek(video, time);
          canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
          var score = sharpness(canvas, small);
          if (score > bestScore) {
            bestScore = score;
            bestTime = time;
            best.getContext("2d").drawImage(canvas, 0, 0);
          }
        }
        // Keep even near-flat frames (variance below 20); the server judges usability.
        var blob = await jpeg(best);
        data.append("frames", blob, "frame-" + (i < 9 ? "0" : "") + (i + 1) + ".jpg");
        times.push(bestTime.toFixed(1));
        var img = document.createElement("img");
        var url = URL.createObjectURL(blob);
        urls.push(url);
        img.alt = "Frame " + (i + 1) + " of 10";
        img.style.height = "64px";
        img.src = url;
        frames.appendChild(img);
        status.textContent = "Reading your video: " + (i + 1) + " of 10";
      }
      data.append("times", times.join(","));
      data.append("duration", duration.toFixed(1));
      status.textContent = "Muse Spark is drafting your listing…";
      var res;
      try {
        res = await fetch(form.action, { method: "POST", body: data });
      } catch (error) { throw new Error(network); }
      if (!res.ok) {
        var message;
        try { message = await res.text(); } catch (error) { throw new Error(network); }
        try {
          var body = JSON.parse(message);
          if (body.detail) message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
        } catch (error) {}
        throw new Error(message || "The upload couldn't be processed. Please try again.");
      }
      location.href = res.url;  // no fragment, so the page reloads even though it is at #film; the draft comes first
    } catch (error) {
      form.classList.add("bad");
      status.textContent = error.message || unreadable;
    } finally {
      video.pause();
      video.removeAttribute("src");
      video.load();
      video.remove();
      urls.forEach(function (url) { URL.revokeObjectURL(url); });
      form.classList.remove("busy");
      input.disabled = false;
      input.value = "";
    }
  });
})();

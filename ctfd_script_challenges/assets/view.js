var MAX_FILE_SIZE = 10000

CTFd._internal.challenge.preRender = function() {}
CTFd._internal.challenge.postRender = function() {
  $("#challenge-input").change((e)=>{
    $("#chal-submit").addClass("disabled-button");
    $("#chal-submit").prop("disabled", true);
    let files = $("#challenge-input").prop("files")
    if (files.length < 1) {
      return
    }
    if (files[0].size > MAX_FILE_SIZE) {
      flash("file size exceeds limit", "danger", 10000)
      $("#challenge-input").val('');
      return
    }

    /*
    You may do client side type checking here, but there may be issues with browsers not correctly supporting
    script file types. (A specific bug was detected with python and chrome). Disable and use server side validation for now


    if (!files[0].type.startsWith("text/")) {
      flash("file type " + files[0].type + " not accepted", "danger", 10000)
      $("#challenge-input").val('');
      return
    }
    */

    $("#chal-submit").removeClass("disabled-button");
    $("#chal-submit").prop("disabled", false);
  });

  $("#chal-submit").click(post_challenge_attempt);
  get_script_results();
};

// We dont want to submit the challenges for real
CTFd._internal.challenge.submit = function(preview) {};

/* Flash a message to the user */
function flash(message, style, timeout) {
  const result_notification = $("#result-notification");
  result_notification.removeClass().addClass("alert alert-dismissable text-center");
  result_notification.addClass("alert-"+style); // no class checking here. just use one of bootstraps styles (danger, info, etc)
  $("#result-message").text(message);
  if (timeout == undefined) {
    timeout = 5000;
  }
  result_notification.slideDown();
  if (timeout > 0) {
    setTimeout((e)=>{
      $(".alert").slideUp();
    }, timeout);
  }
}

/* Submits the script to the server */
function post_challenge_attempt() {
  var challenge_id = parseInt(CTFd.lib.$("#challenge-id").val());
  let url = CTFd.api.domain + "/scripts/challenges/" + challenge_id + "/attempt";
  let headers = {
    "CSRF-Token": init.csrfNonce,
  };

  // Disable the button
  $("#chal-submit").addClass("disabled-button");
  $("#chal-submit").prop("disabled", true);
  let files = $("#challenge-input").prop("files")
  console.log(files)
  if (files.length < 1) {
    return
  }

  let formData = new FormData();
  formData.append("file", files[0]),
  fetch(url, {
    method: "POST",
    headers: headers,
    body: formData
  })
  .then(response => {
    // https://stackoverflow.com/questions/47267221/fetch-response-json-and-response-status
    return response.json().then(data=>({status: response.status, body:data}));
  })
  .then((data) => {
    let status = data.body.status
    let message = data.body.message
    /* Possible status codes:
    authentication_required
    accepted
    not_accepted
    already_solved
    */
    if (status === "authenication_required") {
      window.location =
        CTFd.config.urlRoot +
        "/login?next=" +
        CTFd.config.urlRoot +
        window.location.pathname +
        window.location.hash;
      return;
    } else if (status === "not_accepted") {
      flash(message, "danger")
    } else if (status === "already_solved") {
      flash(message, "info")
    } else if (status === "accepted") {
      flash(message, "success", -1)
      setTimeout((e)=>{
        $("#submission-tab").click()
      }, 500)
      start_results_loop();
    } else {
      flash(message, "warning")
    }
  })
  .catch(error => {
  });
}

/* Check for new results from teh script upload every 5 seconds until it solves, fails, or times out */
function start_results_loop() {
  get_script_results();
  var loop = setInterval(()=>{
      get_script_results(loop)
  }, 5000);
}

/* Get the most recent script results from the server. This loop should stop once the script has timed out or completed */
function get_script_results(loop) {
  var challenge_id = parseInt(CTFd.lib.$("#challenge-id").val());
  let url = CTFd.api.domain + "/scripts/submissions/" + challenge_id;
  let headers = {
    "Accept": ["application/json"],
    "Content-Type": ["application/json"],
    "CSRF-Token": init.csrfNonce,
  };
  fetch(url, {
    method: "GET",
    headers: headers,
  })
  .then(response => {
    // https://stackoverflow.com/questions/47267221/fetch-response-json-and-response-status
    return response.json().then(data=>({status: response.status, body:data}));
  })
  .then((data) => {
    if (data.status !== 200) {
      $("#submission-tab").addClass("disabled").html("Last Submission")
      clearInterval(loop)
      return
    }
    // set the icon appropriately
    let result = data.body.data;

    let icon_class = "";
    if (result.status === "running" || result.status === "submitted") {
      icon_class = "fas fa-sync fa-spin";
      result.output = "script is running...";
    } else if (result.status === "solved" || result.status === "correct") {
      icon_class = "fas fa-check-circle";
      if (loop) {flash("Challenge solved successfully", "success", 15000)}
      clearInterval(loop)
    } else {
      if (loop) {flash("Submission did not pass tests", "danger", 15000)}
      icon_class = "fas fa-exclamation-triangle";
      clearInterval(loop)
    }

    $("#submission-tab").removeClass("disabled").html(
      "<i class=\""+icon_class+"\"></i> Last Submission"
    )
    $("#submission-results").val(result.output);
    //$("#submission-script").val(result.content);
    $("#download-btn").attr("href", result.content);
  })
  .catch(error => {
    clearInterval(loop)
  });
}

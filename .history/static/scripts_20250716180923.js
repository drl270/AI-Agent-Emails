document.addEventListener("DOMContentLoaded", () => {
  console.log("scripts.js loaded"); // Debug: Confirm script execution

  // DOM elements
  const emailForm = document.getElementById("emailForm");
  const submitButton = document.getElementById("submitButton");
  const emailId = document.getElementById("emailId");
  const subject = document.getElementById("subject");
  const message = document.getElementById("message");
  const emailSelect = document.getElementById("emailSelect");
  const submitText = document.getElementById("submitText");
  const loadingSpinner = document.getElementById("loadingSpinner");
  const responseCard = document.getElementById("responseCard");
  const responseEmailId = document.getElementById("responseEmailId");
  const responseCategory = document.getElementById("responseCategory");
  const responseText = document.getElementById("responseText");

  // Verify DOM elements
  if (
    !emailForm ||
    !submitButton ||
    !emailId ||
    !subject ||
    !message ||
    !emailSelect
  ) {
    console.error("DOM elements missing:", {
      emailForm: !!emailForm,
      submitButton: !!submitButton,
      emailId: !!emailId,
      subject: !!subject,
      message: !!message,
      emailSelect: !!emailSelect,
    });
    return;
  }

  // Function to check if all required fields are filled
  const checkFormValidity = () => {
    const isValid =
      emailId.value.trim() && subject.value.trim() && message.value.trim();
    console.log("checkFormValidity:", {
      isValid,
      emailId: emailId.value,
      subject: subject.value,
      message: message.value,
    });
    submitButton.disabled = !isValid;
  };

  // Add input event listeners
  emailId.addEventListener("input", () => {
    console.log("emailId input:", emailId.value);
    checkFormValidity();
  });
  subject.addEventListener("input", () => {
    console.log("subject input:", subject.value);
    checkFormValidity();
  });
  message.addEventListener("input", () => {
    console.log("message input:", message.value);
    checkFormValidity();
  });

  // Load data.csv and populate email dropdown
  console.log("Attempting to load /static/data.csv");
  Papa.parse("/static/data.csv", {
    download: true,
    header: true,
    complete: function (results) {
      console.log("Parsed data:", results.data);
      console.log("Errors:", results.errors);
      results.data.forEach((email) => {
        console.log("Processing email:", email);
        if (email.email_id && email.subject && email.message) {
          const option = document.createElement("option");
          option.value = email.email_id;
          option.textContent = `${email.email_id}: ${email.subject}`;
          emailSelect.appendChild(option);
        } else {
          console.warn("Skipping email due to missing fields:", email);
        }
      });
      checkFormValidity();
    },
    error: function (error) {
      console.error("Error loading /static/data.csv:", error);
      alert("Failed to load email list. Please try manual input.");
    },
  });

  // Handle email selection
  emailSelect.addEventListener("change", () => {
    console.log("emailSelect changed:", emailSelect.value);
    if (emailSelect.value) {
      Papa.parse("/static/data.csv", {
        download: true,
        header: true,
        complete: function (results) {
          console.log("Parsed data for selection:", results.data);
          const selectedEmail = results.data.find(
            (email) => email.email_id === emailSelect.value
          );
          if (selectedEmail) {
            emailId.value = selectedEmail.email_id;
            subject.value = selectedEmail.subject;
            message.value = selectedEmail.message;
            console.log("Selected email populated:", selectedEmail);
            checkFormValidity();
          } else {
            console.warn("Selected email not found:", emailSelect.value);
          }
        },
        error: function (error) {
          console.error("Error loading /static/data.csv:", error);
          alert("Failed to load email list. Please try manual input.");
        },
      });
    } else {
      emailForm.reset();
      submitButton.disabled = true;
      console.log("Form reset due to empty email selection");
    }
  });

  // Handle form submission
  emailForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    console.log("Form submitted:", {
      emailId: emailId.value,
      subject: subject.value,
      message: message.value,
    });
    submitButton.disabled = true;
    submitText.textContent = "Sending...";
    loadingSpinner.classList.remove("d-none");

    const emailData = {
      email_id: emailId.value,
      subject: subject.value,
      message: message.value,
    };

    try {
      const response = await fetch("/process_email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(emailData),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
      }

      const data = await response.json();
      responseEmailId.textContent = data.email_id;
      responseCategory.textContent = data.category;
      responseText.textContent = data.response;
      responseCard.classList.remove("d-none");
      emailForm.reset();
      emailSelect.value = "";
      submitButton.disabled = true;
      console.log("Form submission successful:", data);
    } catch (error) {
      console.error("Error sending email:", error);
      alert("Failed to send email. Please try again later.");
    } finally {
      submitText.textContent = "Send Email";
      loadingSpinner.classList.add("d-none");
    }
  });
});

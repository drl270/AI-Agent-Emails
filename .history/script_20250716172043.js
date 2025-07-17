document.addEventListener("DOMContentLoaded", () => {
  const emailForm = document.getElementById("emailForm");
  const submitButton = document.getElementById("submitButton");
  const emailId = document.getElementById("emailId");
  const subject = document.getElementById("subject");
  const message = document.getElementById("message");

  // Function to check if all required fields are filled
  const checkFormValidity = () => {
    submitButton.disabled = !(
      emailId.value.trim() &&
      subject.value.trim() &&
      message.value.trim()
    );
  };

  // Add input event listeners to all required fields
  emailId.addEventListener("input", checkFormValidity);
  subject.addEventListener("input", checkFormValidity);
  message.addEventListener("input", checkFormValidity);

  // Load data.csv and populate email dropdown
  Papa.parse("data.csv", {
    download: true,
    header: true,
    complete: function (results) {
      const emailSelect = document.getElementById("emailSelect");
      results.data.forEach((email) => {
        if (email.email_id && email.subject && email.message) {
          const option = document.createElement("option");
          option.value = email.email_id;
          option.textContent = `${email.email_id}: ${email.subject}`;
          emailSelect.appendChild(option);
        }
      });
    },
    error: function (error) {
      console.error("Error loading data.csv:", error);
      alert("Failed to load email list. Please try manual input.");
    },
  });

  // Handle email selection
  const emailSelect = document.getElementById("emailSelect");
  emailSelect.addEventListener("change", () => {
    if (emailSelect.value) {
      Papa.parse("data.csv", {
        download: true,
        header: true,
        complete: function (results) {
          const selectedEmail = results.data.find(
            (email) => email.email_id === emailSelect.value
          );
          if (selectedEmail) {
            emailId.value = selectedEmail.email_id;
            subject.value = selectedEmail.subject;
            message.value = selectedEmail.message;
            checkFormValidity(); // Update button state after filling fields
          }
        },
      });
    } else {
      // Clear fields and disable button when no email is selected
      emailForm.reset();
      submitButton.disabled = true;
    }
  });

  // Handle form submission
  const submitText = document.getElementById("submitText");
  const loadingSpinner = document.getElementById("loadingSpinner");
  const responseCard = document.getElementById("responseCard");
  const responseEmailId = document.getElementById("responseEmailId");
  const responseCategory = document.getElementById("responseCategory");
  const responseText = document.getElementById("responseText");

  emailForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    submitButton.disabled = true;
    submitText.textContent = "Sending...";
    loadingSpinner.classList.remove("d-none");

    const emailData = {
      email_id: emailId.value,
      subject: subject.value,
      message: message.value,
    };

    try {
      const response = await fetch("http://127.0.0.1:8000/process_email", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
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
      emailForm.reset(); // Clear the form fields
      emailSelect.value = ""; // Reset the dropdown
      submitButton.disabled = true; // Disable the button after submission
    } catch (error) {
      console.error("Error sending email:", error);
      alert("Failed to send email. Please try again later.");
    } finally {
      submitText.textContent = "Send Email";
      loadingSpinner.classList.add("d-none");
    }
  });
});

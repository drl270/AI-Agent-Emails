document.addEventListener("DOMContentLoaded", () => {
  console.log("scripts.js loaded");

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

  // Function to check form validity
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
  emailId.addEventListener("input", checkFormValidity);
  subject.addEventListener("input", checkFormValidity);
  message.addEventListener("input", checkFormValidity);

  // Fallback emails
  const fallbackEmails = [
    {
      email_id: "test123",
      subject: "Test Complaint",
      message: "I have a complaint about my order.",
    },
    {
      email_id: "test456",
      subject: "Order Status",
      message: "Please provide an update on my order status.",
    },
    {
      email_id: "test789",
      subject: "Random Question",
      message: "I have a random question.",
    },
    {
      email_id: "test101",
      subject: "Product Inquiry",
      message: "Tell me about your products.",
    },
    {
      email_id: "test102",
      subject: "Order Request",
      message: "I want to order 2 units of product ABC1234.",
    },
  ];

  // Load data.csv and populate email dropdown
  console.log("Attempting to load /static/data.csv");
  Papa.parse("/static/data.csv", {
    download: true,
    header: true,
    complete: function (results) {
      console.log("Parsed data:", results.data);
      console.log("Errors:", results.errors);
      let emails = results.errors.length > 0 ? fallbackEmails : results.data;
      emails.forEach((email, index) => {
        console.log(`Processing email ${index}:`, email);
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
      fallbackEmails.forEach((email, index) => {
        console.log(`Processing fallback email ${index}:`, email);
        const option = document.createElement("option");
        option.value = email.email_id;
        option.textContent = `${email.email_id}: ${email.subject}`;
        emailSelect.appendChild(option);
      });
      checkFormValidity();
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
          let selectedEmail = results.data.find(
            (email) => email.email_id === emailSelect.value
          );
          if (!selectedEmail) {
            selectedEmail = fallbackEmails.find(
              (email) => email.email_id === emailSelect.value
            );
          }
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
          const selectedEmail = fallbackEmails.find(
            (email) => email.email_id === emailSelect.value
          );
          if (selectedEmail) {
            emailId.value = selectedEmail.email_id;
            subject.value = selectedEmail.subject;
            message.value = selectedEmail.message;
            console.log("Selected fallback email populated:", selectedEmail);
            checkFormValidity();
          }
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
      const response = await fetch("http://127.0.0.1:8000/process_email", {
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
      responseText.textContent = `Error: ${error.message}`;
      responseCard.classList.remove("d-none");
    } finally {
      submitText.textContent = "Send Email";
      loadingSpinner.classList.add("d-none");
      checkFormValidity();
    }
  });
});

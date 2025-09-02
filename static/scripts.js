function populateOrdersContainer(products_purchase) {
  const ordersContainer = document.getElementById("ordersContainer");
  const orderTotal = document.getElementById("orderTotal");

  ordersContainer.innerHTML = "";

  let total = 0;

  products_purchase.forEach((product) => {
    const orderItem = document.createElement("div");
    orderItem.className = "order-item";

    const nameSpan = document.createElement("span");
    nameSpan.className = "order-field";
    nameSpan.textContent = product.product_name;

    const quantitySpan = document.createElement("span");
    quantitySpan.className = "order-field";
    quantitySpan.textContent = product.quantity;

    const idSpan = document.createElement("span");
    idSpan.className = "order-field";
    idSpan.textContent = product.product_id;

    const priceSpan = document.createElement("span");
    priceSpan.className = "order-field";
    priceSpan.textContent = `$${product.price}`;

    orderItem.appendChild(nameSpan);
    orderItem.appendChild(quantitySpan);
    orderItem.appendChild(idSpan);
    orderItem.appendChild(priceSpan);

    ordersContainer.appendChild(orderItem);

    total += product.quantity * product.price;
  });

  orderTotal.textContent = total.toFixed(2);
}

function populateSuggestionsContainer(products_recommendations) {
  const suggestionsContainer = document.getElementById("suggestionsContainer");

  suggestionsContainer.innerHTML = "";

  products_recommendations.forEach((product) => {
    const suggestionItem = document.createElement("div");
    suggestionItem.className = "suggestion-item";

    const nameSpan = document.createElement("span");
    nameSpan.className = "suggestion-field";
    nameSpan.textContent = product.product_name;

    const idSpan = document.createElement("span");
    idSpan.className = "suggestion-field";
    idSpan.textContent = `ID: ${product.product_id}`;

    const priceSpan = document.createElement("span");
    priceSpan.className = "suggestion-field";
    priceSpan.textContent = `$${product.price}`;

    suggestionItem.appendChild(nameSpan);
    suggestionItem.appendChild(idSpan);
    suggestionItem.appendChild(priceSpan);

    suggestionsContainer.appendChild(suggestionItem);
  });
}

const fallbackEmails = [
  {
    email_id: "1",
    subject: "Order Status Inquiry",
    message:
      "Hi, I wanted to check on the status of my recent order. Can you please let me know when it will be shipped?",
  },
  {
    email_id: "2",
    subject: "Product Return Request",
    message:
      "I need to return a product I purchased last week. What is your return policy and process?",
  },
  {
    email_id: "3",
    subject: "Size Exchange",
    message:
      "I ordered a medium shirt but need to exchange it for a large. How can I do this?",
  },
];

document.addEventListener("DOMContentLoaded", () => {
  console.log("scripts.js loaded");

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

  emailId.addEventListener("input", checkFormValidity);
  subject.addEventListener("input", checkFormValidity);
  message.addEventListener("input", checkFormValidity);

  console.log("Attempting to load /static/data.csv");
  Papa.parse("/static/data.csv", {
    download: true,
    header: true,
    skipEmptyLines: true,
    complete: function (results) {
      console.log("Parsed data:", results.data);
      console.log("Errors:", results.errors);

      let emails = results.data;

      if (emails && emails.length > 0) {
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
      } else {
        console.warn("No emails found in CSV, using fallback data");
        // Use fallback data if CSV is empty
        fallbackEmails.forEach((email, index) => {
          console.log(`Processing fallback email ${index}:`, email);
          const option = document.createElement("option");
          option.value = email.email_id;
          option.textContent = `${email.email_id}: ${email.subject}`;
          emailSelect.appendChild(option);
        });
      }
      checkFormValidity();
    },
    error: function (error) {
      console.error("Error loading /static/data.csv:", error);
      // Use fallback data when CSV fails to load
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

  emailSelect.addEventListener("change", () => {
    console.log("emailSelect changed:", emailSelect.value);
    if (emailSelect.value) {
      Papa.parse("/static/data.csv", {
        download: true,
        header: true,
        skipEmptyLines: true,
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
      const response = await fetch("http://3.20.206.137:8000/process_email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(emailData),
      });

      /*try {
      const response = await fetch("http://localhost:8000/process_email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(emailData),
      }); */

      if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
      }

      const data = await response.json();
      responseEmailId.textContent = data.email_id;
      responseCategory.textContent = data.category;
      responseText.textContent = data.response;
      responseCard.classList.remove("d-none");
      populateOrdersContainer(data.products_purchase);
      populateSuggestionsContainer(data.products_recommendations);
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

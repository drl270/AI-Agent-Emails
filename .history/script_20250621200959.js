document.addEventListener('DOMContentLoaded', () => {
    // Load data.csv and populate email dropdown
    Papa.parse('data.csv', {
        download: true,
        header: true,
        complete: function(results) {
            const emailSelect = document.getElementById('emailSelect');
            results.data.forEach(email => {
                if (email.email_id && email.subject && email.message) {
                    const option = document.createElement('option');
                    option.value = email.email_id;
                    option.textContent = `${email.email_id}: ${email.subject}`;
                    emailSelect.appendChild(option);
                }
            });
        },
        error: function(error) {
            console.error('Error loading data.csv:', error);
            alert('Failed to load email list. Please try manual input.');
        }
    });

    // Handle email selection
    const emailSelect = document.getElementById('emailSelect');
    emailSelect.addEventListener('change', () => {
        if (emailSelect.value) {
            Papa.parse('data.csv', {
                download: true,
                header: true,
                complete: function(results) {
                    const selectedEmail = results.data.find(email => email.email_id === emailSelect.value);
                    if (selectedEmail) {
                        document.getElementById('emailId').value = selectedEmail.email_id;
                        document.getElementById('subject').value = selectedEmail.subject;
                        document.getElementById('message').value = selectedEmail.message;
                    }
                }
            });
        }
    });

    // Handle form submission
    const emailForm = document.getElementById('emailForm');
    const submitButton = document.getElementById('submitButton');
    const submitText = document.getElementById('submitText');
    const loadingSpinner = document.getElementById('loadingSpinner');
    const responseCard = document.getElementById('responseCard');
    const responseEmailId = document.getElementById('responseEmailId');
    const responseCategory = document.getElementById('responseCategory');
    const responseText = document.getElementById('responseText');

    emailForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        submitButton.disabled = true;
        submitText.textContent = 'Sending...';
        loadingSpinner.classList.remove('d-none');

        const emailData = {
            email_id: document.getElementById('emailId').value,
            subject: document.getElementById('subject').value,
            message: document.getElementById('message').value
        };

        try {
            const response = await fetch('http://127.0.0.1:8000/process_email', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(emailData)
            });

            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }

            const data = await response.json();
            responseEmailId.textContent = data.email_id;
            responseCategory.textContent = data.category;
            responseText.textContent = data.response;
            responseCard.classList.remove('d-none');
            emailForm.reset();
            emailSelect.value = '';
        } catch (error) {
            console.error('Error sending email:', error);
            alert('Failed to send email. Please try again later.');
        } finally {
            submitButton.disabled = false;
            submitText.textContent = 'Send Email';
            loadingSpinner.classList.add('d-none');
        }
    });
});
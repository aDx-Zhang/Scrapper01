// Main JavaScript for Polish Marketplace Scraper

document.addEventListener('DOMContentLoaded', function() {
    console.log('Polish Marketplace Scraper initialized');

    // Request notification permission on page load
    if ("Notification" in window) {
        Notification.requestPermission();
    }

    // Handle "Add to Monitor" buttons
    document.addEventListener('click', function(e) {
        const button = e.target.closest('.add-to-monitor');
        if (button) {
            const itemData = {
                url: button.dataset.url,
                title: button.dataset.title,
                price: parseFloat(button.dataset.price),
                currency: button.dataset.currency,
                marketplace: button.dataset.marketplace,
                location: button.dataset.location
            };

            fetch('/monitor/add', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(itemData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('Item added to monitor successfully!');
                    e.target.disabled = true;
                    e.target.textContent = 'Added to Monitor';
                } else {
                    alert('Failed to add item to monitor: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error adding item to monitor');
            });
        }
    });

    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Handle search form
    const searchForm = document.querySelector('#search-form');
    if (searchForm) {
        searchForm.addEventListener('submit', function(e) {
            const keywords = document.querySelector('input[name="keywords"]').value.trim();
            if (!keywords) {
                e.preventDefault();
                alert('Please enter search keywords');
            }
        });
    }

    // Dynamic price range slider
    const priceRange = document.querySelector('#price-range');
    const priceValue = document.querySelector('#price-value');
    if (priceRange && priceValue) {
        priceRange.addEventListener('input', function() {
            priceValue.textContent = priceRange.value + ' PLN';
        });
    }

    // Marketplace toggle switches
    const marketplaceToggles = document.querySelectorAll('.marketplace-toggle');
    marketplaceToggles.forEach(toggle => {
        toggle.addEventListener('change', function() {
            const marketplaceId = this.dataset.marketplaceId;
            const isEnabled = this.checked;

            fetch('/toggle-marketplace/' + marketplaceId, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    is_enabled: isEnabled
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const statusBadge = document.querySelector('#marketplace-status-' + marketplaceId);
                    if (statusBadge) {
                        statusBadge.textContent = isEnabled ? 'Enabled' : 'Disabled';
                        statusBadge.className = 'badge ' + (isEnabled ? 'bg-success' : 'bg-danger');
                    }
                } else {
                    console.error('Failed to toggle marketplace:', data.error);
                    this.checked = !isEnabled; // Revert toggle
                }
            })
            .catch(error => {
                console.error('Error:', error);
                this.checked = !isEnabled; // Revert toggle
            });
        });
    });

    // Feature toggle switches
    const featureToggles = document.querySelectorAll('.feature-toggle');
    featureToggles.forEach(toggle => {
        toggle.addEventListener('change', function() {
            const featureId = this.dataset.featureId;
            const isEnabled = this.checked;

            fetch('/toggle-feature/' + featureId, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    is_enabled: isEnabled
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const statusBadge = document.querySelector('#feature-status-' + featureId);
                    if (statusBadge) {
                        statusBadge.textContent = isEnabled ? 'Enabled' : 'Disabled';
                        statusBadge.className = 'badge ' + (isEnabled ? 'bg-success' : 'bg-danger');
                    }
                } else {
                    console.error('Failed to toggle feature:', data.error);
                    this.checked = !isEnabled; // Revert toggle

                    if (data.premium_required) {
                        alert('This feature requires a premium subscription.');
                    }
                }
            })
            .catch(error => {
                console.error('Error:', error);
                this.checked = !isEnabled; // Revert toggle
            });
        });
    });

    // Mark notifications as read
    const notificationLinks = document.querySelectorAll('.notification-item');
    notificationLinks.forEach(link => {
        link.addEventListener('click', function() {
            const notificationId = this.dataset.notificationId;

            fetch('/mark-notification-read/' + notificationId, {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.classList.remove('notification-unread');
                }
            })
            .catch(error => {
                console.error('Error marking notification as read:', error);
            });
        });
    });

    // AJAX search for test scraper
    const testScraperForm = document.querySelector('#test-scraper-form');
    const searchResults = document.querySelector('#search-results');
    const loadingSpinner = document.querySelector('#loading-spinner');

    if (testScraperForm && searchResults && loadingSpinner) {
        testScraperForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const formData = new FormData(testScraperForm);
            const searchParams = new URLSearchParams();

            for (const pair of formData.entries()) {
                searchParams.append(pair[0], pair[1]);
            }

            // Show loading spinner
            loadingSpinner.classList.remove('d-none');
            searchResults.innerHTML = '';

            fetch('/api/search?' + searchParams.toString())
                .then(response => response.json())
                .then(data => {
                    loadingSpinner.classList.add('d-none');

                    if (data.error) {
                        searchResults.innerHTML = `<div class="alert alert-danger">${data.error}</div>`;
                        return;
                    }

                    if (data.results.length === 0) {
                        searchResults.innerHTML = `<div class="alert alert-info">No results found.</div>`;
                        return;
                    }

                    let resultsHtml = '<div class="row">';

                    data.results.forEach(item => {
                        resultsHtml += `
                            <div class="col-md-4 mb-4">
                                <div class="card search-result h-100">
                                    <img src="${item.image_url || '/static/img/no-image.png'}" class="card-img-top p-2" alt="${item.title}">
                                    <div class="card-body">
                                        <span class="badge marketplace-badge marketplace-badge-${item.marketplace.toLowerCase()}">${item.marketplace}</span>
                                        <h5 class="card-title mt-2">${item.title}</h5>
                                        <p class="price">${item.price.toLocaleString()} ${item.currency}</p>
                                        <p class="card-text small text-muted">${item.location || 'Location not specified'}</p>
                                    </div>
                                    <div class="card-footer bg-transparent">
                                        <a href="${item.url}" target="_blank" class="btn btn-primary btn-sm">View Listing</a>
                                    </div>
                                </div>
                            </div>
                        `;
                    });

                    resultsHtml += '</div>';
                    searchResults.innerHTML = resultsHtml;
                })
                .catch(error => {
                    loadingSpinner.classList.add('d-none');
                    searchResults.innerHTML = `<div class="alert alert-danger">Error while searching: ${error}</div>`;
                    console.error('Error:', error);
                });
        });
    }


    // Added testTelegram function -  placed near other test functions (assumed intention)
    function testTelegram() {
        fetch('/settings/test/telegram', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if(data.success) {
                alert('Telegram configuration is working!');
            } else {
                alert('Failed to test Telegram: ' + data.error);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error testing Telegram configuration');
        });
    }

    function testEmail() {
        const form = document.getElementById('emailConfigForm');
    }

    // Function to show desktop notification
    function showDesktopNotification(title, message) {
        if (!("Notification" in window)) {
            console.log("This browser does not support desktop notifications");
            return;
        }

        if (Notification.permission === "granted") {
            new Notification(title, {
                body: message,
                icon: '/static/img/icon.png'
            });
        } else if (Notification.permission !== "denied") {
            Notification.requestPermission().then(function (permission) {
                if (permission === "granted") {
                    new Notification(title, {
                        body: message,
                        icon: '/static/img/icon.png'
                    });
                }
            });
        }
    }

    // Function to check for new notifications
    function checkNotifications() {
        fetch('/notifications/unread')
            .then(response => response.json())
            .then(data => {
                if (data.notifications && data.notifications.length > 0) {
                    data.notifications.forEach(notification => {
                        showDesktopNotification(notification.title, notification.message);
                    });
                }
            })
            .catch(error => console.error('Error:', error));
    }

    // Check for new notifications every minute
    setInterval(checkNotifications, 60000);
});
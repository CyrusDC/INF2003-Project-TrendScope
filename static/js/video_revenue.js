/* static/js/video_revenue.js */

// ==========================================
// 1. Client-Side Numbered Pagination (20/page)
// ==========================================
document.addEventListener('DOMContentLoaded', function () {
    const tableBody = document.getElementById('tier-table-body');
    const nav = document.getElementById('pagination-nav');
    const indicator = document.getElementById('page-indicator');

    // Only run if tier table exists on this view
    if (!tableBody || !nav || !indicator) return;

    const rowsPerPage = 20;
    const rows = Array.from(tableBody.querySelectorAll('.tier-row'));
    const totalRows = rows.length;
    const totalPages = Math.ceil(totalRows / rowsPerPage);
    let currentPage = 1;

    function renderPage(page) {
        currentPage = page;
        const start = (page - 1) * rowsPerPage;
        const end = start + rowsPerPage;

        // Toggle visibility of rows
        rows.forEach((row, index) => {
            row.style.display = (index >= start && index < end) ? '' : 'none';
        });

        // Update counter label
        const currentEnd = Math.min(end, totalRows);
        indicator.textContent = `Showing ${start + 1}–${currentEnd} of ${totalRows} records`;

        renderPaginationButtons();
    }

    function renderPaginationButtons() {
        nav.innerHTML = '';
        if (totalPages <= 1) return;

        // Previous button
        const prevLi = document.createElement('li');
        prevLi.className = `page-item ${currentPage === 1 ? 'disabled' : ''}`;
        prevLi.innerHTML = `<a class="page-link" href="javascript:void(0)">&laquo; Prev</a>`;
        prevLi.addEventListener('click', () => { if (currentPage > 1) renderPage(currentPage - 1); });
        nav.appendChild(prevLi);

        // Numbered buttons window
        let startPage = Math.max(1, currentPage - 2);
        let endPage = Math.min(totalPages, currentPage + 2);

        if (startPage > 1) {
            addPageButton(1);
            if (startPage > 2) addEllipsis();
        }

        for (let p = startPage; p <= endPage; p++) {
            addPageButton(p);
        }

        if (endPage < totalPages) {
            if (endPage < totalPages - 1) addEllipsis();
            addPageButton(totalPages);
        }

        // Next button
        const nextLi = document.createElement('li');
        nextLi.className = `page-item ${currentPage === totalPages ? 'disabled' : ''}`;
        nextLi.innerHTML = `<a class="page-link" href="javascript:void(0)">Next &raquo;</a>`;
        nextLi.addEventListener('click', () => { if (currentPage < totalPages) renderPage(currentPage + 1); });
        nav.appendChild(nextLi);
    }

    function addPageButton(pageNumber) {
        const li = document.createElement('li');
        li.className = `page-item ${pageNumber === currentPage ? 'active' : ''}`;
        li.innerHTML = `<a class="page-link" href="javascript:void(0)">${pageNumber}</a>`;
        li.addEventListener('click', () => renderPage(pageNumber));
        nav.appendChild(li);
    }

    function addEllipsis() {
        const li = document.createElement('li');
        li.className = 'page-item disabled';
        li.innerHTML = `<span class="page-link">...</span>`;
        nav.appendChild(li);
    }

    renderPage(1);
});

// ==========================================
// 2. Video Stats Modal Fetcher
// ==========================================
function loadVideoStats(videoId) {
    const modalEl = document.getElementById('videoStatsModal');
    if (!modalEl) return;
    const modal = new bootstrap.Modal(modalEl);

    document.getElementById('modalVideoId').textContent = videoId;
    document.getElementById('modalLoading').style.display = 'block';
    document.getElementById('modalContent').style.display = 'none';
    modal.show();

    fetch(`/api/video-stats/${encodeURIComponent(videoId)}`)
        .then(response => {
            if (!response.ok) throw new Error('Video record not found');
            return response.json();
        })
        .then(data => {
            // General Info
            document.getElementById('modalChannelId').textContent = data.channel_id ?? 'N/A';
            document.getElementById('modalCreatorTier').textContent = (data.creator_tier || 'N/A').toUpperCase();
            // Display Video Title and Channel Name from Postgres
            document.getElementById('modalVideoId').textContent = data.video_title ? `${data.video_title} (${videoId})` : videoId;
            document.getElementById('modalChannelId').textContent = data.channel_name ? `${data.channel_name} (ID: ${data.channel_id})` : data.channel_id;

            // Monetization Status & Warning Banner Control
            const mon = data.monetization || {};
            const monStatus = String(mon.status || 'unknown').toLowerCase().trim();
            const statusBadge = document.getElementById('modalMonetizationStatus');
            const alertBanner = document.getElementById('modalMonetizationAlert');
            const reasonSpan = document.getElementById('modalMonetizationReason');

            if (monStatus === 'monetized') {
                statusBadge.textContent = 'MONETIZED';
                statusBadge.className = 'badge bg-success';
                if (alertBanner) {
                    alertBanner.style.setProperty('display', 'none', 'important');
                }
            } else {
                statusBadge.textContent = monStatus.replace(/_/g, ' ').toUpperCase();
                statusBadge.className = 'badge bg-danger';

                const rawReason = mon.reason || 'Advertiser Unfriendly / Policy Violation';
                const formattedReason = rawReason.replace(/_/g, ' ')
                    .replace(/\b\w/g, l => l.toUpperCase());

                if (reasonSpan) reasonSpan.textContent = formattedReason;
                if (alertBanner) {
                    alertBanner.style.setProperty('display', 'flex', 'important');
                }
            }

            // Ads Formats & Playback Rate
            const adsData = data.ads || {};
            const playbackRate = adsData.monetized_playback_rate !== undefined 
                ? (adsData.monetized_playback_rate * 100).toFixed(1) + '%' 
                : 'N/A';
            document.getElementById('modalPlaybackRate').textContent = playbackRate;

            const adFormatsContainer = document.getElementById('modalAdFormats');
            adFormatsContainer.innerHTML = '';
            const formats = adsData.formats || [];
            if (formats.length > 0) {
                formats.forEach(format => {
                    const badge = document.createElement('span');
                    if (format.toLowerCase().includes('non-skippable')) {
                        badge.className = 'badge bg-danger text-white px-2 py-1';
                    } else if (format.toLowerCase().includes('bumper')) {
                        badge.className = 'badge bg-warning text-dark px-2 py-1';
                    } else {
                        badge.className = 'badge bg-secondary text-white px-2 py-1';
                    }
                    badge.textContent = format;
                    adFormatsContainer.appendChild(badge);
                });
            } else {
                adFormatsContainer.innerHTML = '<span class="text-muted">No ad formats registered</span>';
            }

            // Revenue Calculations (Platform Ads vs Brand Sponsorships)
            const revSum = data.revenue_summary || {};
            const adGross = Number(revSum.total_gross_usd || 0);
            const sponsorFee = Number(revSum.total_sponsorship_usd || 0);
            const totalCombined = adGross + sponsorFee;

            document.getElementById('modalAdGross').textContent = '$' + adGross.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
            document.getElementById('modalSponsorshipUsd').textContent = '$' + sponsorFee.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
            document.getElementById('modalCreatorPayout').textContent = '$' + Number(revSum.total_creator_usd || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});

            const headerBadge = document.getElementById('modalCombinedGrossBadge');
            if (headerBadge) headerBadge.textContent = '$' + totalCombined.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});

            const totalEarningsElem = document.getElementById('modalTotalVideoEarnings');
            if (totalEarningsElem) totalEarningsElem.textContent = '$' + totalCombined.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});

            // Sponsorships Array
            const sponsorList = document.getElementById('modalSponsorshipList');
            sponsorList.innerHTML = '';
            if (data.sponsorships && data.sponsorships.length > 0) {
                data.sponsorships.forEach(sp => {
                    const li = document.createElement('li');
                    li.className = 'list-group-item d-flex justify-content-between align-items-center';
                    li.innerHTML = `
                      <div>
                        <strong>${sp.brand || 'Unknown Brand'}</strong>
                        <span class="badge bg-secondary ms-2">${sp.disclosed_paid_promotion ? 'Disclosed Paid Promotion' : 'Undisclosed'}</span>
                      </div>
                      <span class="fw-bold text-success">$${Number(sp.fee_usd || 0).toLocaleString()}</span>
                    `;
                    sponsorList.appendChild(li);
                });
            } else {
                sponsorList.innerHTML = '<li class="list-group-item text-muted">No sponsorships recorded.</li>';
            }

            // Country Breakdown Array
            const countryTbody = document.getElementById('modalCountryTableBody');
            countryTbody.innerHTML = '';
            if (data.revenue_by_country && data.revenue_by_country.length > 0) {
                data.revenue_by_country.forEach(c => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                      <td><strong>${c.country_code}</strong></td>
                      <td>${Number(c.source_max_observed_views || 0).toLocaleString()}</td>
                      <td class="text-success">$${Number(c.estimated_gross_usd || 0).toFixed(2)}</td>
                      <td>$${Number(c.creator_usd || 0).toFixed(2)}</td>
                      <td><span class="badge bg-light text-dark border">${c.revenue_recipient || 'none'}</span></td>
                    `;
                    countryTbody.appendChild(tr);
                });
            } else {
                countryTbody.innerHTML = '<tr><td colspan="5" class="text-muted text-center">No country breakdown available</td></tr>';
            }

            document.getElementById('modalLoading').style.display = 'none';
            document.getElementById('modalContent').style.display = 'block';
        })
        .catch(err => {
            document.getElementById('modalLoading').innerHTML = `<div class="alert alert-danger m-3">${err.message}</div>`;
        });
}

function filterOptions(filterElemId, targetSelectId) {
    const filterElem = document.getElementById(filterElemId);
    const targetSelect = document.getElementById(targetSelectId);

    if (!filterElem || !targetSelect) return;

    const selectedTier = filterElem.value.toLowerCase().trim();
    const options = targetSelect.querySelectorAll('option');

    options.forEach((opt, index) => {
        // Keep the placeholder '-- Choose Video --'
        if (index === 0) return;

        const optTier = (opt.getAttribute('data-tier') || '').toLowerCase().trim();

        if (selectedTier === 'all' || optTier === selectedTier) {
            opt.style.display = '';
        } else {
            opt.style.display = 'none';
            if (opt.selected) {
                targetSelect.value = ''; // Reset selection if current selection gets hidden
            }
        }
    });
}
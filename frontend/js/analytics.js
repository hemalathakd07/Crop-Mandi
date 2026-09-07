/**
 * Analytics page functionality - fetches real data from backend API
 * No hardcoded values - all data comes from verified providers
 */

(function() {
  "use strict";

  // State management
  let currentCommodity = "coffee"; // Start with coffee since cardamom is not supported
  let currentSeries = "Arabica Parchment"; // Default coffee series
  let currentLocation = "Sakleshpur";
  let currentDays = 30;
  let latestData = null;
  let historyData = null;
  let marketData = null;
  let predictionData = null;
  let priceChart = null;

  // DOM elements
  const elements = {
    commoditySelect: null,
    varietySelect: null,
    stateSelect: null,
    timeSelect: null,
    applyFiltersBtn: null,
    avgPriceCard: null,
    aiPredictionCard: null,
    bestApmcCard: null,
    marketTrendCard: null,
    priceTrendChart: null,
    regionalHeatmap: null,
    marketComparisonTable: null,
    loadingIndicator: null,
  };

  // Initialize on DOM ready
  document.addEventListener("DOMContentLoaded", function() {
    initializeElements();
    attachEventListeners();
    loadAnalyticsData();
  });

  function initializeElements() {
    // Get select elements properly
    const selects = document.querySelectorAll('select');
    if (selects.length >= 4) {
      elements.commoditySelect = selects[0]; // First select is Crop
      elements.varietySelect = selects[1];  // Second select is Variety
      elements.stateSelect = selects[2];    // Third select is State
      elements.timeSelect = selects[3];     // Fourth select is Time
    }
    
    elements.applyFiltersBtn = document.querySelector('button');
    
    // Find card elements by their content
    const cards = document.querySelectorAll('.bg-surface-container-lowest');
    if (cards.length >= 4) {
      elements.avgPriceCard = cards[0];
      elements.aiPredictionCard = cards[1];
      elements.bestApmcCard = cards[2];
      elements.marketTrendCard = cards[3];
    }
    
    elements.priceTrendChart = document.getElementById('priceTrendChart');
    elements.marketComparisonTable = document.querySelector('table tbody');
    
    // Chart title elements
    elements.chartTitle = document.getElementById('chart-title');
    elements.chartSubtitle = document.getElementById('chart-subtitle');
  }

  function attachEventListeners() {
    if (elements.applyFiltersBtn) {
      elements.applyFiltersBtn.addEventListener('click', handleApplyFilters);
    }
    
    // Add change listeners to select elements
    const selects = document.querySelectorAll('select');
    selects.forEach(select => {
      select.addEventListener('change', handleFilterChange);
    });
  }

  function handleFilterChange() {
    // Auto-refresh on filter change
    loadAnalyticsData();
  }

  function handleApplyFilters() {
    loadAnalyticsData();
  }

  function getSelectedFilters() {
    const selects = document.querySelectorAll('select');
    let commodity = "cardamom";
    let location = "Sakleshpur";
    let days = 30;
    
    selects.forEach(select => {
      const value = select.value;
      if (value.includes("Crop:")) {
        const cropName = value.replace("Crop: ", "").toLowerCase();
        // Map display names to API commodity names
        if (cropName.includes("cardamom")) {
          commodity = "cardamom";
        } else if (cropName.includes("coffee")) {
          commodity = "coffee";
        } else if (cropName.includes("pepper")) {
          commodity = "pepper";
        }
      } else if (value.includes("State:")) {
        // For now, we'll use a default location based on state
        // In a real implementation, this would map states to default locations
        const stateName = value.replace("State: ", "").toLowerCase();
        if (stateName.includes("karnataka")) {
          location = "Sakleshpur"; // Default for Karnataka
        } else if (stateName.includes("kerala")) {
          location = "Idukki"; // Default for Kerala
        }
      } else if (value.includes("Time:")) {
        if (value.includes("7")) days = 7;
        else if (value.includes("30")) days = 30;
        else if (value.includes("YTD")) days = 365;
      }
    });
    
    return { commodity, location, days };
  }

  async function loadAnalyticsData() {
    const filters = getSelectedFilters();
    currentCommodity = filters.commodity;
    currentLocation = filters.location;
    currentDays = filters.days;
    
    showLoadingState();
    
    try {
      // Load data from existing backend endpoints
      await Promise.all([
        loadLatestPrices(),
        loadHistoricalData(),
        loadMarketComparison(),
        loadPrediction()
      ]);
      
      updateUI();
    } catch (error) {
      console.error("Failed to load analytics data:", error);
      showNoDataState(error.message);
    } finally {
      hideLoadingState();
    }
  }

  async function loadLatestPrices() {
    try {
      latestData = await CropMandiAPI.getLatestPrices(currentCommodity);
    } catch (error) {
      console.error("Failed to load latest prices:", error);
      latestData = null;
    }
  }

  async function loadHistoricalData() {
    try {
      // Get the appropriate series for the commodity
      const series = getSeriesForCommodity(currentCommodity);
      if (series) {
        const endDate = new Date().toISOString().split('T')[0];
        const startDate = new Date(Date.now() - currentDays * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
        
        historyData = await CropMandiAPI.getPriceHistory(currentCommodity, series);
      }
    } catch (error) {
      console.error("Failed to load historical data:", error);
      historyData = null;
    }
  }

  async function loadMarketComparison() {
    try {
      if (currentLocation) {
        marketData = await CropMandiAPI.getMarketPrices(currentCommodity, currentLocation);
      }
    } catch (error) {
      console.error("Failed to load market comparison:", error);
      marketData = null;
    }
  }

  async function loadPrediction() {
    try {
      const series = getSeriesForCommodity(currentCommodity);
      if (series) {
        predictionData = await CropMandiAPI.getNextSessionEstimate(currentCommodity, series);
      }
    } catch (error) {
      console.error("Failed to load prediction:", error);
      predictionData = null;
    }
  }

  function getSeriesForCommodity(commodity) {
    // Map commodities to their default series
    switch (commodity) {
      case "coffee":
        return "Arabica Parchment";
      case "pepper":
        return "Cochin Garbled";
      case "cardamom":
        return null; // Cardamom not supported
      default:
        return null;
    }
  }

  function showLoadingState() {
    // Show loading indicators
    document.body.style.cursor = "wait";
    
    // Update cards to show loading
    if (elements.avgPriceCard) {
      const priceEl = elements.avgPriceCard.querySelector('h3');
      if (priceEl) priceEl.textContent = "Loading...";
    }
    
    if (elements.aiPredictionCard) {
      const predEl = elements.aiPredictionCard.querySelector('h3');
      if (predEl) predEl.textContent = "Loading...";
    }
    
    if (elements.bestApmcCard) {
      const locationEl = elements.bestApmcCard.querySelector('h3');
      if (locationEl) locationEl.textContent = "Loading...";
    }
    
    if (elements.marketTrendCard) {
      const trendEl = elements.marketTrendCard.querySelector('.font-bold');
      if (trendEl) trendEl.textContent = "Loading...";
    }
  }

  function hideLoadingState() {
    document.body.style.cursor = "default";
  }

  function showNoDataState(reason) {
    hideLoadingState();
    
    // Update all cards to show no data
    if (elements.avgPriceCard) {
      const priceEl = elements.avgPriceCard.querySelector('h3');
      if (priceEl) priceEl.textContent = "No verified data available";
    }
    
    if (elements.aiPredictionCard) {
      const predEl = elements.aiPredictionCard.querySelector('h3');
      if (predEl) predEl.textContent = "Prediction unavailable";
    }
    
    if (elements.bestApmcCard) {
      const locationEl = elements.bestApmcCard.querySelector('h3');
      if (locationEl) locationEl.textContent = "No verified market data";
    }
    
    if (elements.marketTrendCard) {
      const trendEl = elements.marketTrendCard.querySelector('.font-bold');
      if (trendEl) trendEl.textContent = "Trend unavailable";
    }
    
    // Clear chart
    if (priceChart) {
      priceChart.destroy();
      priceChart = null;
    }
    
    // Clear market comparison table
    if (elements.marketComparisonTable) {
      elements.marketComparisonTable.innerHTML = `
        <tr>
          <td colspan="5" class="p-4 text-center text-on-surface-variant">
            ${reason || "No verified market data available"}
          </td>
        </tr>
      `;
    }
  }

  function updateUI() {
    // Check if we have any data at all
    const hasAnyData = latestData || historyData || marketData || predictionData;
    
    if (!hasAnyData) {
      showNoDataState("No verified data available");
      return;
    }
    
    // Update chart title with commodity name
    if (elements.chartTitle) {
      const commodityName = currentCommodity.charAt(0).toUpperCase() + currentCommodity.slice(1);
      elements.chartTitle.textContent = `${commodityName} Price Trend`;
    }
    if (elements.chartSubtitle) {
      const unit = historyData?.unit || latestData?.observations?.[0]?.unit || 'Qtl';
      elements.chartSubtitle.textContent = `${currentDays}-day historical data (₹/${unit})`;
    }
    
    updateKPICards();
    updatePriceTrendChart();
    updateMarketComparison();
    updateRegionalHeatmap();
  }

  function updateKPICards() {
    // Average Price Card
    if (elements.avgPriceCard && analyticsData.latest) {
      const priceEl = elements.avgPriceCard.querySelector('h3');
      const trendEl = elements.avgPriceCard.querySelector('.font-data-tabular');
      
      if (priceEl && analyticsData.latest.price) {
        const formattedPrice = formatCurrency(analyticsData.latest.price, analyticsData.latest.unit);
        priceEl.textContent = formattedPrice;
        
        if (trendEl && analyticsData.trend_percentage !== null) {
          const sign = analyticsData.trend_percentage >= 0 ? "+" : "";
          trendEl.innerHTML = `
            <span class="material-symbols-outlined text-sm mr-1" data-icon="${analyticsData.trend_percentage >= 0 ? 'trending_up' : 'trending_down'}">
              ${analyticsData.trend_percentage >= 0 ? 'trending_up' : 'trending_down'}
            </span>
            <span>${sign}${analyticsData.trend_percentage.toFixed(1)}% vs last period</span>
          `;
        }
      }
    }
    
    // AI Prediction Card
    if (elements.aiPredictionCard) {
      const predEl = elements.aiPredictionCard.querySelector('h3');
      const descEl = elements.aiPredictionCard.querySelector('.font-data-tabular');
      
      if (analyticsData.prediction) {
        const pred = analyticsData.prediction;
        if (predEl) {
          const sign = pred.percentage_change >= 0 ? "+" : "";
          predEl.textContent = `${sign}${pred.percentage_change.toFixed(1)}%`;
        }
        if (descEl) {
          descEl.textContent = pred.note || "AI-based price forecast";
        }
      } else {
        if (predEl) predEl.textContent = "Prediction unavailable";
        if (descEl) descEl.textContent = "Insufficient verified data for prediction";
      }
    }
    
    // Best APMC Rate Card
    if (elements.bestApmcCard && analyticsData.market_comparison.length > 0) {
      const bestMarket = analyticsData.market_comparison[0];
      const locationEl = elements.bestApmcCard.querySelector('h3');
      const priceEl = elements.bestApmcCard.querySelector('.font-data-tabular');
      
      if (locationEl) {
        locationEl.textContent = bestMarket.market;
      }
      if (priceEl && bestMarket.price) {
        const unit = bestMarket.unit || "Qtl";
        priceEl.textContent = formatCurrency(bestMarket.price, unit);
      }
    }
    
    // Market Trend Card
    if (elements.marketTrendCard) {
      const trendEl = elements.marketTrendCard.querySelector('.font-bold');
      const descEl = elements.marketTrendCard.querySelector('.text-label-sm');
      
      if (analyticsData.trend) {
        if (trendEl) {
          trendEl.textContent = analyticsData.trend;
        }
        if (descEl) {
          descEl.textContent = getTrendDescription(analyticsData.trend);
        }
      } else {
        if (trendEl) trendEl.textContent = "Trend unavailable";
        if (descEl) descEl.textContent = "Insufficient data for trend analysis";
      }
    }
  }

  function updatePriceTrendChart() {
    if (!elements.priceTrendChart || !analyticsData.historical.length) {
      return;
    }
    
    const ctx = elements.priceTrendChart.getContext('2d');
    
    // Destroy existing chart
    if (priceChart) {
      priceChart.destroy();
    }
    
    // Prepare data
    const labels = analyticsData.historical.map(point => {
      const date = new Date(point.date);
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    });
    
    const prices = analyticsData.historical.map(point => point.price);
    
    // Create gradient
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(0, 69, 50, 0.4)');
    gradient.addColorStop(1, 'rgba(0, 69, 50, 0.0)');
    
    // Create chart
    priceChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Historical Price',
            data: prices,
            borderColor: '#004532',
            backgroundColor: gradient,
            borderWidth: 3,
            pointBackgroundColor: '#ffffff',
            pointBorderColor: '#004532',
            pointBorderWidth: 2,
            pointRadius: 4,
            pointHoverRadius: 6,
            fill: true,
            tension: 0.4
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false,
        },
        plugins: {
          legend: {
            display: true,
            position: 'bottom',
            labels: {
              font: {
                family: "'Roboto', sans-serif",
                size: 12
              },
              color: '#3f4944'
            }
          },
          tooltip: {
            backgroundColor: 'rgba(27, 28, 26, 0.9)',
            titleFont: { family: "'Roboto', sans-serif", size: 13 },
            bodyFont: { family: "'Roboto', sans-serif", size: 14, weight: 'bold' },
            padding: 12,
            cornerRadius: 8,
            callbacks: {
              label: function(context) {
                let label = context.dataset.label || '';
                if (label) {
                  label += ': ';
                }
                if (context.parsed.y !== null) {
                  // Get unit from the first data point if available
                  const unit = analyticsData.historical[0]?.unit || 'Qtl';
                  const formattedValue = new Intl.NumberFormat('en-IN', { 
                    maximumSignificantDigits: 3 
                  }).format(context.parsed.y);
                  label += `₹${formattedValue} / ${unit}`;
                }
                return label;
              }
            }
          }
        },
        scales: {
          x: {
            grid: {
              display: false,
            },
            ticks: {
              font: { family: "'Roboto', sans-serif", size: 11 },
              color: '#6f7973'
            }
          },
          y: {
            grid: {
              color: 'rgba(0, 69, 50, 0.05)',
              drawBorder: false,
            },
            ticks: {
              font: { family: "'Roboto', sans-serif", size: 11 },
              color: '#6f7973',
              callback: function(value, index, values) {
                // Use the actual unit from data instead of hardcoded 'k'
                const unit = analyticsData.historical[0]?.unit || analyticsData.latest?.unit || 'Qtl';
                if (unit === 'Qtl' || unit === 'Quintal') {
                  return '₹' + value / 1000 + 'k';
                } else if (unit === 'kg') {
                  return '₹' + value;
                } else {
                  return '₹' + value;
                }
              }
            }
          }
        }
      }
    });
  }

  function updateMarketComparison() {
    if (!elements.marketComparisonTable || !analyticsData.market_comparison.length) {
      return;
    }
    
    const tbody = elements.marketComparisonTable;
    tbody.innerHTML = '';
    
    analyticsData.market_comparison.forEach((market, index) => {
      const row = document.createElement('tr');
      row.className = 'hover:bg-surface-container-lowest/50 transition-colors border-b border-outline-variant/10 group';
      
      // Generate initials for market icon
      const initials = market.market.substring(0, 2).toUpperCase();
      
      // Calculate prediction (simplified - in real app would use actual prediction API)
      const predictionChange = market.prediction_change || 0;
      const predictionPrice = market.price ? market.price * (1 + predictionChange / 100) : null;
      
      // Determine action signal based on trend
      const actionSignal = getActionSignal(analyticsData.trend);
      
      row.innerHTML = `
        <td class="p-4 flex items-center gap-2">
          <div class="w-8 h-8 rounded bg-primary/10 text-primary flex items-center justify-center shrink-0">
            <span class="text-xs font-bold font-body-md">${initials}</span>
          </div>
          <span class="text-on-surface font-semibold group-hover:text-primary transition-colors">${market.market}</span>
        </td>
        <td class="p-4 text-on-surface">${market.price ? formatCurrency(market.price, market.unit || 'Qtl') : 'N/A'}</td>
        <td class="p-4 text-on-surface-variant">${market.type || 'N/A'}</td>
        <td class="p-4">
          ${predictionPrice ? `
            <div class="flex items-center ${predictionChange >= 0 ? 'text-surface-tint' : 'text-error'}">
              <span class="material-symbols-outlined text-sm mr-1" data-icon="${predictionChange >= 0 ? 'trending_up' : 'trending_down'}">
                ${predictionChange >= 0 ? 'trending_up' : 'trending_down'}
              </span>
              <span>${formatCurrency(predictionPrice, market.unit || 'Qtl')} (${predictionChange >= 0 ? '+' : ''}${predictionChange.toFixed(1)}%)</span>
            </div>
          ` : 'N/A'}
        </td>
        <td class="p-4">
          <div class="inline-flex items-center justify-center ${getActionSignalClasses(actionSignal)} px-3 py-1 rounded-full font-label-sm text-xs font-bold tracking-wide">
            ${actionSignal}
          </div>
        </td>
      `;
      
      tbody.appendChild(row);
    });
  }

  function updateRegionalHeatmap() {
    // For now, this is a placeholder - the regional heatmap visualization
    // would need to be implemented with actual mapping coordinates
    // The data is available in analyticsData.regional_data
    console.log("Regional data available:", analyticsData.regional_data);
  }

  function formatCurrency(value, unit = null) {
    if (value === null || value === undefined) {
      return 'N/A';
    }
    
    // Format the number without currency symbol since we'll add unit separately
    const formattedNumber = new Intl.NumberFormat('en-IN', {
      maximumFractionDigits: 0
    }).format(value);
    
    // Add appropriate unit if provided
    if (unit) {
      return `₹${formattedNumber} / ${unit}`;
    }
    
    return `₹${formattedNumber}`;
  }

  function getTrendDescription(trend) {
    switch (trend) {
      case 'BULLISH':
        return 'High demand from exporters.';
      case 'BEARISH':
        return 'Market showing downward pressure.';
      case 'NEUTRAL':
        return 'Market stable with minor fluctuations.';
      default:
        return 'Trend analysis unavailable.';
    }
  }

  function getActionSignal(trend) {
    switch (trend) {
      case 'BULLISH':
        return 'SELL';
      case 'BEARISH':
        return 'WAIT';
      case 'NEUTRAL':
        return 'HOLD';
      default:
        return 'WAIT';
    }
  }

  function getActionSignalClasses(signal) {
    switch (signal) {
      case 'SELL':
        return 'bg-tertiary text-on-tertiary shadow-[inset_0_1px_1px_rgba(255,255,255,0.4),0_2px_4px_rgba(114,32,0,0.3)]';
      case 'HOLD':
        return 'bg-secondary-container text-on-secondary-container shadow-[0_0_8px_rgba(255,195,41,0.5)]';
      case 'WAIT':
        return 'bg-surface-variant text-on-surface-variant shadow-[inset_1px_2px_4px_rgba(0,0,0,0.1)]';
      default:
        return 'bg-surface-variant text-on-surface-variant';
    }
  }

})();
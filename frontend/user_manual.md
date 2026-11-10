# AirSense User Manual

**AirSense tells you how clean or polluted the air is in an Indian city, and what to do about it.**
You give it pollutant readings; it gives you a category (Good → Severe), a confidence score and simple health advice.
No technical knowledge is needed.

---

## 1. Opening the app
Open the address your administrator gave you (usually `http://localhost:8501`) in any web browser, on a computer, tablet or phone.
The menu on the left has four pages: **Predict**, **Batch (CSV)**, **Pipeline** and **Help**.
At the bottom of the menu a coloured box shows whether the service is **online** (green) or **offline** (red).

## 2. Checking one city (Predict page)
1. **Choose a city** from the dropdown.
2. **Pick a date** (today is pre-selected). Air quality follows the seasons, so the date matters a little.
3. **Type the readings you have.** Each box shows its unit. Hover over the **?** for a plain-English explanation.
   - You need **at least 2 readings**. Leave the rest blank - AirSense fills them in with typical values for that city.
   - **CO is in milligrams (mg/m³)**; all others are micrograms (µg/m³). This is the most common mistake.
4. Press **Predict air quality**.

> **Don't have readings handy?** Press one of the three **example buttons** above the form to fill it in and see how the app works.

## 3. Reading your result
| Colour | Category | What it means |
|---|---|---|
| 🟢 Dark green | **Good** | Little or no health impact |
| 🟩 Light green | **Satisfactory** | Minor discomfort for very sensitive people |
| 🟨 Yellow | **Moderate** | Discomfort for people with asthma, heart or lung disease |
| 🟧 Orange | **Poor** | Breathing discomfort on prolonged exposure |
| 🟥 Red | **Very Poor** | Illness on prolonged exposure - avoid outdoor exercise |
| 🟫 Dark red | **Severe** | Affects everyone - stay indoors |

- **Confidence** is how sure the model is (higher is better). If it is below 60% you will see a yellow warning - check your numbers.
- **What this means for you** gives short advice, plus a note for children, older adults and people with breathing or heart conditions.
- Click **How sure is the model about each category?** to see the full breakdown.

## 4. Many rows at once (Batch page)
1. Click **Download CSV template** and open it in Excel or Google Sheets.
2. Fill one row per city/day. Columns: `City, Date, PM2.5, PM10, NO2, SO2, CO, O3`. Date is optional; readings may be blank (at least 2 per row).
3. Save as CSV, then **upload** it. You will see a preview of the first 10 rows.
4. Press **Run predictions**. You get a colour-coded table, a chart, and a **Download results** button.
5. If some rows have problems (for example an unsupported city or a negative number), they are listed with their **CSV row number** and the reason. The good rows are still predicted - fix the bad ones and upload again.

## 5. Pipeline page (for administrators)
Shows how the system is built and run: the pipeline diagram (green = last run OK, red = failed), run history with failures, data-processing speed, experiment history and model quality. Buttons open the MLflow experiment tracker and the Grafana live dashboard.

## 6. Troubleshooting
| You see | Do this |
|---|---|
| "Service offline" / "isn't responding" | Wait a minute and refresh. If it persists, tell your administrator. |
| "Please enter at least 2 readings" | Fill in at least two boxes. |
| Red message about a field | A number is out of range (negative or impossibly large). Check units, especially CO. |
| "City … is not supported" | Choose a city from the dropdown; for CSVs use the exact city names. |
| "File couldn't be read" | Re-save as plain **CSV** and use the template columns. |

## 7. Good to know
- Results are **estimates for information**, not an official CPCB reading, and not medical advice.
- Readings are used only to make the prediction; they are not tied to your identity.
- Cities available are those the model was trained on (the dropdown lists them).

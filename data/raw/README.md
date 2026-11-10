# data/raw - put the real dataset here

Download **Air Quality Data in India (2015-2020)** from Kaggle and copy `city_day.csv` into this folder:

    cp ~/Downloads/archive/city_day.csv data/raw/city_day.csv
    dvc repro            # re-runs automatically because this folder changed

If the file is absent, the pipeline generates **synthetic** demo data and labels it as such
(`metrics/data_quality.json` -> `"source": "synthetic"`, and the UI shows a warning banner).
This folder is an *input only*: nothing in the pipeline ever overwrites or deletes your file.
The CSV is git-ignored (do not commit the dataset; cite the Kaggle source instead).

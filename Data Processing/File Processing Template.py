import pandas as pd
#Needs to be a full file path ending with [instert file name].csv
df = pd.read_csv(FILENAME)
#Example labels used for the drought files. Remember that "elif" only executes if no other condition is detected, multiple "ifs" can trigger if their conditions are met. 
df['Drought ID'] = 'Operation Conditions:'
for index, row in df.iterrows():
    if row['drought_below_5_percentile'] != 0 :
        df.at[index, 'Drought ID'] += ' drought below 5 percentile'
    if row['drought_below_10_percentile'] !=0:
        df.at[index, 'Drought ID'] += ' drought below 10 percentile'
    if row['drought_below_10_percent'] != 0:
        df.at[index, 'Drought ID'] += ' drought below 10 percent'
    if row['drought_below_25_percent'] != 0:
        df.at[index, 'Drought ID'] += ' drought below 25 percent'
    if row['drought_below_50_percent'] != 0:
        df.at[index, 'Drought ID'] += ' drought below 50 percent'
    if row['drought_below_75_percent'] != 0:
        df.at[index, 'Drought ID'] += ' drought below 75 percent'
    else:
        df.at[index, 'Drought ID'] = 'normal operation'
#if you want to overwrite the new file, keep the path an name the same, otherwise, change the filename. 
df.to_csv(NEWFILENAME, index=False)
#Take a look at what it made.
df = pd.read_csv(NEWFILENAME)
print(df)
print("Done")

#!/usr/bin/env python3

import os
import argparse
import boto3
import datetime
import configparser
import csv

######## correct plotting
import matplotlib
matplotlib.use('Agg')
######## plotting
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import scipy
from sklearn.linear_model import LinearRegression


AVOID_PROFILES = []
PLOT_COLORS = ['blue', 'green', 'red', 'magenta', 'black']
SUMMARY = {}
ACCOUNT_SERVICES = {}


def gather_profiles():
    config = configparser.ConfigParser()
    config.read('.aws/credentials')
    profiles = []
    for account in config.items():
        if account[0].lower() in AVOID_PROFILES:
            continue
        profiles.append(account[0])
    print('== All Available Profiles:', ','.join(profiles))
    return profiles


def gather_cost_results(cost_client):
    now = datetime.datetime.utcnow()
    start = (now - datetime.timedelta(days=180)).strftime('%Y-%m-%d')
    end = now.strftime('%Y-%m-%d')
    results = []
    token = None
    while True:
        if token:
            kwargs = {'NextPageToken': token}
        else:
            kwargs = {}
        try:
            data = cost_client.get_cost_and_usage(TimePeriod={'Start': start, 'End': end}, Granularity='MONTHLY',
                                              Metrics=['UnblendedCost'],
                                              GroupBy=[{'Type': 'DIMENSION', 'Key': 'LINKED_ACCOUNT'},
                                                       {'Type': 'DIMENSION', 'Key': 'SERVICE'}], **kwargs)
            results += data['ResultsByTime']
            token = data.get('NextPageToken')
        except Exception as ex:
            print("!!! An error occurred. Could be that the account doesn't have Cost Explorer capabilities.")
            print(ex)
            AVOID_PROFILES.append(cost_client)
            break
        if not token:
            break
    print("=== Success in gathering costs.")
    return results


def generate_csv(gathered_results, account):
    ACCOUNT_SERVICES[account] = {}
    SUMMARY[account] = ""
    csv_data = [['Year', 'Month', 'TotalCost']]
    unit = 'USD'

    for result_by_time in gathered_results:
        total_amount = 0
        for group in result_by_time['Groups']:
            amount = group['Metrics']['UnblendedCost']['Amount']
            service = group['Keys'][1]
            total_amount += float(amount)
            dater = datetime.datetime.strptime(result_by_time['TimePeriod']['Start'], '%Y-%m-%d')
            # set up summary
            # SUMMARY[account] += '\n' + dater.strftime("%B") + ' - ' + '\t'.join(group['Keys']) + \
            #                     ' = ' + amount + ' (' + unit + ')'
            # if it is not an estimated cost than calculate trend
            if not result_by_time['Estimated']:
                if service not in ACCOUNT_SERVICES[account]:
                    ACCOUNT_SERVICES[account][service] = []
                ACCOUNT_SERVICES[account][service].append(amount)

        dater = datetime.datetime.strptime(result_by_time['TimePeriod']['Start'], '%Y-%m-%d')
        SUMMARY[account] += '\n' + '==== Total cost in ' + dater.strftime("%B") + ' of ' + \
                            str(dater.year) + ' = ' + str(total_amount) + ' (' + str(unit) + ')'
        csv_data.append([str(dater.year), dater.strftime("%B")[:3], str(total_amount)])

    csv_file = open('csvs/monthly_%s.csv' % account, 'w')
    with csv_file:
        writer = csv.writer(csv_file)
        writer.writerows(csv_data)
    print("=== Success in creating the CSV:", 'csvs/monthly_%s.png' % account)


def generate_profile_plot(account):
    articles_df = pd.read_csv('csvs/monthly_%s.csv' % account)
    plt.xticks(np.arange(len(articles_df['Month'])), tuple(articles_df['Month']), rotation=10)
    plt.ylabel(account)
    plt.grid(True)
    plt.plot(articles_df['TotalCost'], 'o-')

    plt.suptitle('Monthly Costs per Account (USD)', fontsize='large')
    os.makedirs('pngs', exist_ok=True)
    plt.savefig('pngs/monthly_%s.png' % account, dpi=300, format='png')
    plt.clf()
    print('=== Success in plotting:', 'pngs/monthly_%s.png' % account)


def generate_all_profiles_plot(accounts):
    matrix_y = int(len(accounts) / 3)
    matrix_x = int(len(accounts) / 4 + len(accounts) % 4)
    fig, axs = plt.subplots(nrows=matrix_y, ncols=matrix_x)
    for index, account in enumerate(accounts):
        if account in AVOID_PROFILES:
            continue
        articles_df = pd.read_csv('csvs/monthly_%s.csv' % account)
        plt.subplot(matrix_y, matrix_x, index + 1)
        plt.xticks(np.arange(len(articles_df['Month'])), tuple(articles_df['Month']), rotation=10)
        plt.ylabel(account)
        plt.grid(True)
        plt.plot(articles_df['TotalCost'], 'o-', color=PLOT_COLORS[index % len(PLOT_COLORS)])

    fig.suptitle('Monthly Costs per Account (USD)', fontsize='large')
    dpi = 120
    fig.set_figwidth(1920 / dpi)
    fig.set_figheight(1080 / dpi)
    fig.savefig('pngs/all_plots.png', dpi=dpi, format='png')
    # plt.show()
    print('== Success in plotting all accounts: pngs/all_plots.png')


def summary(account):
    print("=== Summary:", SUMMARY[account])


def decider(profile):
    if profile == 'ALL':
        profiles = gather_profiles()
        os.makedirs('csvs', exist_ok=True)

        for account in profiles:
            print('== Working on', account, '...')
            try:
                boto3.setup_default_session(profile_name=account)
            except Exception as ex:
                print('!!! The config profile {0} could not be found !'.format(account))
                print(ex)
                AVOID_PROFILES.append(account)
                continue
            cost_client = boto3.client('ce', 'us-east-1')
            cost_results = gather_cost_results(cost_client)
            generate_csv(cost_results, account)
            generate_profile_plot(account)
            summary(account)
            calculate_service_trend(account)
            print("== Done!")
            print()
        generate_all_profiles_plot(profiles)


def calculate_service_trend(account):
    print("=== Trends:")
    for service in ACCOUNT_SERVICES[account]:
        series = ACCOUNT_SERVICES[account][service]
        if len(series) < 2:
            continue
        x = [float(i) for i in range(0, len(series))]
        y = [float(i) for i in series]
        slope, intercept, r_value, p_value, std_err = scipy.stats.linregress(x, y)

        message = ""
        if slope > 10:
            message = "[RED] VERY SIGNIFICANT INCREASE in costs!!!"
        elif slope > 1:
            message = "[ORANGE] SIGNIFICANT INCREASE in costs!!"
        elif 0.5 < slope < 1:
            message = "[YELLOW] INCREASE in costs!"
        elif 0 <= slope <= 0.5:
            message = "[GREEN] No change in costs."
        elif slope < 0:
            message = "[BLUE] DECREASE in costs!"
        print("==== %s: %s" % (service, message))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', type=str, default="")
    args = parser.parse_args()
    if not args.profile:
        print('= You must specify a --profile. Use ALL for running on all profiles')
        exit(1)
    if args.profile == "ALL":
        print('= You intended to extract costs from every account available.')

    decider(args.profile)

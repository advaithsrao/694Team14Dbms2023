import sys
import os
import pandas as pd
import json
from datetime import datetime
import numpy as np

root_folder = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_folder)

from utils import connSQL,connNoSQL



def fetch_searched_tweet_metadata_user_data(SQL_client,user_id):

    query=f'''SELECT t.*, u.name, u.screen_name,u.verified, 
            (SELECT COUNT(r.retweet_id) FROM retweets r WHERE r.tweet_id = t.tweet_id) AS retweet_count,
            (SELECT COUNT(q.quoted_tweet_id) FROM quoted_tweets q WHERE q.tweet_id = t.tweet_id) AS quoted_count,
            (SELECT COUNT(p.reply_tweet_id) FROM reply p WHERE p.tweet_id = t.tweet_id) AS reply_count
            FROM tweets t
            JOIN user_profile u ON t.user_id = u.user_id
            WHERE
            u.user_id='{user_id}'
            '''
    
    print(query)

    #run the query
    relational_data_df=pd.read_sql_query(query,con=SQL_client)
    return(relational_data_df)
    
def fetch_searched_tweets_data(NoSQL_client,filtered_tweet_ids):
    # Construct Elasticsearch Query DSL
    search_query = {
                "query": {
                    "bool": {
                    "filter": []
                    }
                },
                "_source": [
                    "id_str",
                    "text",
                    "entities.hashtags.text",
                    "possibly_sensitive",
                    "entities.media.type",
                    "entities.media.url"
                ],
                "size":10000
                }
    
    # Conditionally include the terms query for id_str
    if(len(filtered_tweet_ids)):
        search_query["query"]["bool"]["filter"].append({
            "terms": {
            "id_str": filtered_tweet_ids
            }
        })

    # Convert query to JSON string
    search_query_json = json.dumps(search_query)
    print(search_query_json)

    # Execute the search query and retrieve the sorted results
    response = NoSQL_client.search(index="index__*", body=search_query_json)
    sorted_hits = response["hits"]["hits"]
    searched_tweets_data = pd.DataFrame.from_records(sorted_hits)
    
    if(searched_tweets_data.empty):
        return(searched_tweets_data)
    
    # Extracting  'possibly_sensitive'
    searched_tweets_data['possibly_sensitive'] = searched_tweets_data['_source'].apply(lambda x:x['possibly_sensitive'])
    
    # Extracting 'id_str'
    searched_tweets_data['id_str'] = searched_tweets_data['_source'].apply(lambda x:x['id_str'])

    # Extracting hashtags
    def get_hashtags(row):
        text_list = []
        if('entities' in row.keys()):
            if('hashtags' in row['entities']):
                hash_list = row['entities']['hashtags']
                for i in hash_list:
                    text_list.append(i['text'])
                return text_list
            else:
                return np.nan
        else:
            return np.nan
        
    searched_tweets_data['hashtags'] = searched_tweets_data['_source'].apply(get_hashtags)
    
    # Extracting text
    searched_tweets_data['text'] = searched_tweets_data['_source'].apply(lambda x:x['text'])

    # Extracting 'media_type'
    def get_media_type(row):
        if 'entities' in row.keys():
            if 'media' in row['entities']:
                if 'type' in row['entities']['media'][0].keys():
                    return row['entities']['media'][0]['type']
                else:
                    return np.nan
            else:
                return np.nan
        else:
            return np.nan
    searched_tweets_data['media_type'] = searched_tweets_data['_source'].apply(get_media_type)

    # Extracting 'media_url'
    def get_media_url(row):
        if 'entities' in row.keys():
            if 'media' in row['entities']:
                if 'url' in row['entities']['media'][0].keys():
                    return row['entities']['media'][0]['url']
                else:
                    return np.nan
            else:
                return np.nan
        else:
            return np.nan
        
    
    searched_tweets_data['media_url'] = searched_tweets_data['_source'].apply(get_media_url)


    # Create a list of desired columns
    desired_columns = ['id_str', 'text', 'hashtags', 'possibly_sensitive','media_type','media_url']

    #Filtering desired columns from dataframe
    existing_desired_columns = [col for col in desired_columns if col in searched_tweets_data.columns]
    searched_tweets_data = searched_tweets_data[existing_desired_columns]
    
    #Renaming tweet id column
    searched_tweets_data = searched_tweets_data.rename(columns={'id_str': 'tweet_id'})
    return(searched_tweets_data)


def fetch_user_results(user_id):
    SQL_client=connSQL()
    NoSQL_client=connNoSQL()
    filtered_tweet_ids=[]
    searched_tweet_metadata_user_data=fetch_searched_tweet_metadata_user_data(SQL_client,user_id)
    if(searched_tweet_metadata_user_data.empty):
        return(searched_tweet_metadata_user_data,searched_tweet_metadata_user_data,searched_tweet_metadata_user_data,searched_tweet_metadata_user_data)
    filtered_tweet_ids = searched_tweet_metadata_user_data['tweet_id'].values.tolist()
    filtered_tweet_ids=[str(x) for x in filtered_tweet_ids]

    searched_tweets_data=fetch_searched_tweets_data(NoSQL_client,filtered_tweet_ids)
    if(searched_tweets_data.empty):
        return(searched_tweets_data,searched_tweets_data,searched_tweets_data,searched_tweets_data)

    results_df=pd.merge(searched_tweets_data,searched_tweet_metadata_user_data, on='tweet_id', how='inner') 
    results_df=results_df.sort_values(by=['retweet_count'], ascending=False)
    results_df_org=results_df[results_df['tweet_flag'] == 'original_tweet_flag']
    results_df_quoted=results_df[results_df['tweet_flag'] == 'quoted_tweet_flag']
    results_df_retweet=results_df[results_df['tweet_flag'] == 'retweet_flag']
    results_df_reply=results_df[results_df['tweet_flag'] == 'reply_flag']

    return(results_df_org,results_df_quoted,results_df_retweet,results_df_reply)
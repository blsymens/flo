import dash
from dash import dcc, html, Input, Output, State, dash_table
import plotly.graph_objs as go
import pandas as pd
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
import io

load_dotenv()  # Load environment variables

app = dash.Dash(__name__)
server = app.server

# Azure Blob Storage setup
connection_string = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
container_name = os.getenv('AZURE_CONTAINER_NAME')
blob_service_client = BlobServiceClient.from_connection_string(connection_string)
container_client = blob_service_client.get_container_client(container_name)

# Function to read CSV from Azure Blob Storage
def read_csv_from_blob(blob_name,sep=','):
    blob_client = container_client.get_blob_client(blob_name)
    download_stream = blob_client.download_blob()
    return pd.read_csv(io.StringIO(download_stream.content_as_text()),sep=sep)

# Function to write CSV to Azure Blob Storage
def write_csv_to_blob(df, blob_name):
    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)
    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(output.getvalue(), overwrite=True)

# Load data
baby_growth_blob = 'baby_growth_data.csv'
who_data_blob = 'tab_wfa_girls_p_0_13.csv'

try:
    df = read_csv_from_blob(baby_growth_blob)
    df['Date'] = pd.to_datetime(df['Date'])
except:
    df = pd.DataFrame(columns=['Date', 'Age_Days', 'Weight_kg'])

who_data = read_csv_from_blob(who_data_blob,sep=';')

# Process the data to get the percentiles you need
percentiles = {
    '5th': pd.to_numeric(who_data['P5'].str.replace(',', '.'), errors='coerce').tolist(),
    '10th': pd.to_numeric(who_data['P10'].str.replace(',', '.'), errors='coerce').tolist(),
    '50th': pd.to_numeric(who_data['P50'].str.replace(',', '.'), errors='coerce').tolist(),
    '90th': pd.to_numeric(who_data['P90'].str.replace(',', '.'), errors='coerce').tolist(),
    '95th': pd.to_numeric(who_data['P95'].str.replace(',', '.'), errors='coerce').tolist()
}

days = (who_data['Week']*7).tolist()

app.layout = html.Div([
    html.H1("Baby Growth Tracker for Female Infants (WHO Standards)"),
    
    html.Div([
        html.Label("Date of Birth:"),
        dcc.DatePickerSingle(id='dob-picker', date=datetime.now().date() - timedelta(days=14)),
        
        html.Label("Date of Measurement:"),
        dcc.DatePickerSingle(id='date-picker', date=datetime.now().date()),
        
        html.Label("Weight (kg):"),
        dcc.Input(id='weight-input', type='number', placeholder='Enter weight in kg'),
        
        html.Button('Add Record', id='add-button', n_clicks=0)
    ]),
    
    html.Div(id='record-added-message'),
    
    dcc.Graph(id='growth-chart'),
    
    dash_table.DataTable(
        id='data-table',
        columns=[
            {'name': 'Date', 'id': 'Date', 'type': 'datetime'},
            {'name': 'Age (Days)', 'id': 'Age_Days', 'type': 'numeric'},
            {'name': 'Weight (kg)', 'id': 'Weight_kg', 'type': 'numeric'}
        ],
        data=df.to_dict('records'),
        editable=True,
        row_deletable=True
    ),
    
    html.Button('Save Changes', id='save-button', n_clicks=0)
])

@app.callback(
    Output('record-added-message', 'children'),
    Output('growth-chart', 'figure'),
    Output('data-table', 'data'),
    Input('add-button', 'n_clicks'),
    Input('save-button', 'n_clicks'),
    Input('data-table', 'data'),
    State('dob-picker', 'date'),
    State('date-picker', 'date'),
    State('weight-input', 'value')
)
def update_data_and_chart(add_clicks, save_clicks, table_data, dob, date, weight):
    global df
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger_id == 'add-button' and dob and date and weight is not None:
        dob = datetime.strptime(dob, '%Y-%m-%d')
        measurement_date = datetime.strptime(date, '%Y-%m-%d')
        age_days = (measurement_date - dob).days
        
        new_record = pd.DataFrame({'Date': [measurement_date], 'Age_Days': [age_days], 'Weight_kg': [weight]})
        df = pd.concat([df, new_record], ignore_index=True)
        write_csv_to_blob(df, baby_growth_blob)
        message = "Record added successfully!"
    elif trigger_id == 'save-button' or trigger_id == 'data-table':
        df = pd.DataFrame(table_data)
        df['Date'] = pd.to_datetime(df['Date'])
        write_csv_to_blob(df, baby_growth_blob)
        message = "Changes saved successfully!"
    else:
        message = "No changes made."
    
    fig = update_chart()
    return message, fig, df.to_dict('records')

def update_chart():
    fig = go.Figure()
    
    # Fill between 5th and 95th percentile with light grey
    fig.add_trace(go.Scatter(
        x=days + days[::-1],
        y=percentiles['95th'] + percentiles['5th'][::-1],
        fill='toself',
        fillcolor='rgba(200,200,200,0.3)',
        line=dict(color='rgba(255,255,255,0)'),
        hoverinfo="skip",
        showlegend=False
    ))

    # Fill between 10th and 90th percentile with darker grey
    fig.add_trace(go.Scatter(
        x=days + days[::-1],
        y=percentiles['90th'] + percentiles['10th'][::-1],
        fill='toself',
        fillcolor='rgba(150,150,150,0.3)',
        line=dict(color='rgba(255,255,255,0)'),
        hoverinfo="skip",
        showlegend=False
    ))
    
    # Add percentile lines
    for percentile, weights in percentiles.items():
        fig.add_trace(go.Scatter(
            x=days,
            y=weights,
            mode='lines',
            name=f'{percentile} Percentile',
            line=dict(color='rgba(0,0,0,0.5)', width=1)
        ))
    
    if not df.empty:
        fig.add_trace(go.Scatter(
            x=df['Age_Days'],
            y=df['Weight_kg'],
            mode='lines+markers',
            line=dict(color='red', width=2),
            marker=dict(size=6),
            name="Baby's Growth"
        ))
    
    fig.update_layout(
        title='Baby Growth Chart for Female Infants (WHO Standards)',
        xaxis_title='Age (days)',
        yaxis_title='Weight (kg)',
        legend=dict(y=0.5, traceorder='reversed', font_size=16),
        hovermode='x unified'
    )
    
    return fig

if __name__ == '__main__':
    app.run_server(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
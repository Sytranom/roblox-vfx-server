# main.py - Your public VFX Resolution Server

# Import all necessary libraries
import requests
import io
import concurrent.futures
from flask import Flask, request, jsonify
from PIL import Image
from waitress import serve # A production-ready server for Flask

# --- Configuration ---
# CRITICAL: Use a new, alternate Roblox account (a "bot") for this cookie.
# DO NOT use your main account's cookie on a public server.
ROBLOSECURITY_COOKIE = '_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_GgIQAQ.7E3B86CB2E01795C60F7C1E8EB1BCC0C0AE62B73A8394A85C98009B4FAA11DB62686B666825AA86205F4394DDB77097DEFF8E10F2AD9DE806AAEA340384162EEE15278B16F6D05266D068828C8948A3AAE2985822339333F633401AFD75A3E710714CC763559C4941D8FD9E13650B4E2C232DDC48B8C6FE6896A19B11D6A30406978E7AE25D6728259B77AAF07C993C0F12DA9CD8CA2204FB3149A69887B1AFF5073092C3AA527A3782E390965104CD3A170CE35FBFD62830AF42C8E9B3DB800D5B8FEBDFC9B2C0FC3076E54EC3F8E135B06E5265E37922C1283DA02ECBD63BEEFA1C757C65B7EF625BE000B13ECBF31BDB512951490AA42661C4068E062E6F3AEFB2F26BC0F90498F79431BC698492B738C53C90C92F2FAA0B933AECDD047870890BBB1D3EDC2110119808A4B55DE123A87FCECF1EABF38C552FBA19BDD924FEB89F7BBB618220857CD4E77EAB948E5AC66FCD432560C4C44076F8102CFBD6CA271496177EF775B7D3DBED03C3F62F55F27A2E454516B6CC293C439ABF6AEF4225429A1D02AE02291F3B2C8794027D354011A374AEA57ABD8B5640430AEE1B153A287291EC930F222FD394FD4B8809F620C1BE8E00D5DDA8936D5AF57864B14DC978096B35572819FD957060C3CD7DA7C2686C06AA8346A6B4E0EC8BDDDCC11D4880AF7F41133971E17237EC839E263C2F54692FEF200745A5BDAEAB3FCDE0A5626CEA4DABF4CD99248CD38A06A60CA526E30824EED0EDA2BA85F8FB25E79A42B6532E53F73B9BC303CD446F07CB188A1072F086817BE530CE92D64DFE23E3D716A9A4E1B7DC0A708CFC917FEC44664F26C87C74E8181B485F621612BC3378E58FE8056F51C6C0A9CBFEE4DD6EE7BCCA0D1FEEAF64C37F640F087EA0587D52B602FD539E9F64585A00269CC646051EC155F54C3C7B431F067447CAA34223D4C73FAC86FED333E11BE3CEB54CB409F6F0B877C40F5603EFCFDC4C2C3D9070CE3902F79D3DA068736299CC037720F9991CF062629A06D8AB2BF2DB64E4C4FE4F9DE27EE3E956FFBD5528892ABDEDA4FA7BBFD4962CD78AF0E9E80A4F23D66B5D11CF1AE07607BD608479AFE73094FF10733F35D7D2441270B7B1401B080E3EE1309189D6C'



# --- Flask App & Session Setup ---
app = Flask(__name__)

# Create a persistent session to reuse the connection and cookie
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'application/json'
})
session.cookies.update({
    '.ROBLOSECURITY': ROBLOSECURITY_COOKIE
})


# --- Core Logic ---
def fetch_asset_resolution(asset_id: str):
    """
    Fetches a single asset from Roblox and returns its width and height.
    This function is designed to be run in a separate thread.
    """
    api_url = f"https://assetdelivery.roblox.com/v1/asset/?id={asset_id}"
    try:
        # Make the request to download the asset data
        response = session.get(api_url, timeout=10, allow_redirects=True)
        response.raise_for_status() # Raise an error for bad status codes (like 403 Forbidden)

        # Check if the response is empty
        if not response.content:
            print(f"  [EMPTY RESPONSE] Asset {asset_id}")
            return asset_id, None

        # Use Pillow to open the image data from memory and get its size
        with Image.open(io.BytesIO(response.content)) as img:
            width, height = img.size
            print(f"  [SUCCESS] Asset {asset_id}: {width}x{height}")
            # Return the data in a format Lua can understand
            return asset_id, {"x": width, "y": height}

    except Exception as e:
        # This will catch network errors, invalid image data, etc.
        print(f"  [FAILED] Asset {asset_id}: {e}")
        return asset_id, None


# --- API Endpoint Definition ---
@app.route('/get_resolutions', methods=['POST'])
def get_resolutions_endpoint():
    """
    This is the main endpoint that the Roblox plugin will call.
    It receives a list of asset IDs and returns their resolutions.
    """
    print("\nReceived request from Roblox Studio...")
    data = request.json
    if not data or 'asset_ids' not in data:
        return jsonify({"error": "Invalid request format. Expecting {'asset_ids': [...]}"}), 400

    asset_ids = data['asset_ids']
    print(f"Processing {len(asset_ids)} asset IDs...")

    resolutions_map = {}
    # Use a ThreadPoolExecutor to fetch all asset resolutions concurrently for speed
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        # Create a dictionary of future tasks
        future_to_asset = {executor.submit(fetch_asset_resolution, asset_id): asset_id for asset_id in asset_ids}
        # Process results as they are completed
        for future in concurrent.futures.as_completed(future_to_asset):
            asset_id, resolution = future.result()
            if resolution:
                resolutions_map[asset_id] = resolution

    print("...Finished processing. Sending response to Studio.")
    # Return the final map of resolutions as a JSON response
    return jsonify(resolutions_map)


# --- Main Execution Block ---
if __name__ == '__main__':
    # Check if the placeholder cookie is still there
    if 'PASTE_YOUR_BOT_ACCOUNTS_COOKIE_HERE' in ROBLOSECURITY_COOKIE:
        print("\n" + "="*60)
        print("🛑 ERROR: You have not replaced the placeholder .ROBLOSECURITY cookie.")
        print("🛑 Please edit the script and paste your bot account's cookie.")
        print("="*60 + "\n")
    else:
        # This will run when you click the "Run" button on Replit
        print("\n" + "="*60)
        print("✅ Roblox Resolution Server is starting...")
        print("✅ Listening for requests from your plugin.")
        print("="*60 + "\n")
        # Use waitress to serve the Flask app on all available network interfaces
        serve(app, host='0.0.0.0', port=8080)

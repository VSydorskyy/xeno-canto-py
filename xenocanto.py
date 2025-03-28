#!/usr/bin/python3


import json
import os
import shutil
import ssl
import sys
from os.path import join as pjoin
from urllib import error, request

# TODO:
#   [/] Log messages to console
#   [X] Add ability to recognize the area where last download stopped
#   [ ] Purge recordings that did not complete download
#   [ ] Add sono image download capabilities
#   [ ] Display tables of tags collected
#
# FIXME:
#   [X] Fix naming of folders in audio and metadata to be more consistent
#   [X] Fix SSL certificate errors
#   [X] Fix stopping download when file present
#   [X] Fix using matches operator with tags (e.g. cnt:"United States")
#   [ ] Allow the delete method to accept species names with spaces

# Disable certificate verification
ssl._create_default_https_context = ssl._create_unverified_context


def urlretrieve_with_exception(url, filename):
    try:
        request.urlretrieve(url, filename)
    except Exception as e:
        print(f"Failed to download {url} with exception {e}")


# Retrieves metadata for requested recordings in the form of a JSON file
def metadata(filt, inp_path="dataset"):
    page = 1
    page_num = 1
    filt_path = list()
    filt_url = list()
    print("Retrieving metadata...")

    # Scrubbing input for file name and url
    for f in filt:
        filt_url.append(f.replace(" ", "%20"))
        filt_path.append(
            (f.replace(" ", "")).replace(":", "_").replace('"', "")
        )

    path = pjoin(inp_path, "metadata/") + "".join(filt_path)

    # Overwrite metadata query folder
    if not os.path.exists(path):
        os.makedirs(path)

    # Save all pages of the JSON response
    while page < page_num + 1:
        url = "https://www.xeno-canto.org/api/2/recordings?query={0}&page={1}".format(
            "%20".join(filt_url), page
        )
        try:
            r = request.urlopen(url)
        except error.HTTPError as e:
            print("An error has occurred: " + str(e))
            exit()
        print("Downloading metadate page " + str(page) + "...")
        data = json.loads(r.read().decode("UTF-8"))
        filename = path + "/page" + str(page) + ".json"
        with open(filename, "w") as saved:
            json.dump(data, saved)
        page_num = data["numPages"]
        page += 1

    # Return the path to the folder containing downloaded metadata
    return path


# Retrieves metadata and audio recordings
def download(filt, inp_path="dataset"):
    page = 1
    page_num = 1
    print(f"Downloading all recordings for query {filt}...")

    # Retrieve metadata to parse for download links
    path = metadata(filt, inp_path=inp_path)

    # Enumerate list of metadata folders
    path_list = listdir_nohidden(pjoin(inp_path, "metadata/"))
    redown = set()

    # Check for any in_progress files in the metadata folders
    for p in path_list:
        check_path = pjoin(inp_path, "metadata/") + str(p)
        if os.path.isfile(check_path):
            continue

        if os.path.exists(check_path + "/in_progress.txt"):
            curr = open(check_path + "/in_progress.txt")
            line = int(curr.readline())
            if line not in redown:
                redown.add(line)
            curr.close()

    with open(path + "/page" + str(page) + ".json", "r") as jsonfile:
        data = jsonfile.read()
    data = json.loads(data)
    page_num = data["numPages"]
    print(
        "Found "
        + str(data["numRecordings"])
        + " recordings for given query, downloading..."
    )
    while page < page_num + 1:

        with open(path + "/page" + str(page) + ".json", "r") as jsonfile:
            data = jsonfile.read()
        data = json.loads(data)

        for i in range(len((data["recordings"]))):
            # url = 'http:' + data['recordings'][i]['file']
            url = data["recordings"][i]["file"]
            name = (data["recordings"][i]["en"]).replace(" ", "")
            track_id = data["recordings"][i]["id"]

            # Keep track of the most recently downloaded file
            recent = open(path + "/in_progress.txt", "w")
            recent.write(str(track_id))
            recent.write("\n")
            recent.close()

            audio_path = pjoin(inp_path, "audio/") + name + "/"
            audio_file = str(track_id) + ".mp3"

            print(f"File will land in {name} subfolder")

            # If the track has been included in the progress files, it can be corrupt and must be redownloaded regardless
            if int(track_id) in redown:
                print(
                    "File "
                    + str(track_id)
                    + ".mp3 must be redownloaded since it was not completed during a previous query."
                )
                print("Downloading " + str(track_id) + ".mp3")
                urlretrieve_with_exception(url, audio_path + audio_file)
                continue

            if not os.path.exists(audio_path):
                os.makedirs(audio_path)

            # If the file exists in the directory, we will skip it
            if os.path.exists(audio_path + audio_file):
                print(
                    "File "
                    + str(track_id)
                    + ".mp3 is already present. Moving on to the next recording..."
                )
                continue

            print("Downloading " + str(track_id) + ".mp3...")
            urlretrieve_with_exception(url, audio_path + audio_file)

        page += 1

        # If the method has completed successfully, then we can delete the in_progress file
        if os.path.exists(path + "/in_progress.txt"):
            os.remove(path + "/in_progress.txt")
        else:
            if len(data["recordings"]) == 0:
                print("No recordings found for query.")
            else:
                raise RuntimeError("Recording download was not completed.")


# Retrieve all files while ignoring those that are hidden
def listdir_nohidden(path):
    for f in os.listdir(path):
        if not f.startswith("."):
            yield f


# Removes audio folders containing num or less than num files
def purge(num, path="dataset"):
    path = pjoin(path, "audio/")
    dirs = listdir_nohidden(path)
    for fold in dirs:
        fold_path = path + fold
        count = sum(1 for _ in listdir_nohidden(fold_path))
        if count < num:
            print(
                "Folder at "
                + fold_path
                + " has fewer than "
                + num
                + " recordings. Deleting..."
            )
            shutil.rmtree(fold_path)


def delete(filt, path="dataset"):

    # Generating list of current tracks with metadata
    gen_meta()

    # Separating desired tags from values for parsing
    tags = list()
    vals = list()
    for f in filt:
        tag = f.split(":")[0]
        tags.append(tag)

        val = f.split(":")[1]
        if tag == "en":
            val = val.replace("_", " ")
        vals.append(val)

    with open(pjoin(path, "metadata/library.json"), "r") as jsonfile:
        data = jsonfile.read()
    data = json.loads(data)

    # Creating a set of track id's to delete
    track_del = set()
    for i in range(int(data["recordingNumber"])):
        for j in range(len(tags)):
            if data["tracks"][i][str(tags[j])] == str(vals[j]):
                track_del.add(int(data["tracks"][i]["id"]))

    print(str(len(track_del)) + " tracks have been identified to be deleted.")

    # Checking audio folders for tracks to delete
    path = pjoin(path, "audio/")
    dirs = listdir_nohidden(path)
    removed = 0
    for fold in dirs:
        fold_path = path + fold
        tracks = listdir_nohidden(fold_path)
        for tr in tracks:
            if int(tr.split(".")[0]) in track_del:
                os.remove(fold_path + "/" + str(tr))
                removed = removed + 1

    print(str(removed) + " tracks deleted!")

    # Removing any empty folders
    purge(1)


# Generate a metadata file for given library path
def gen_meta(path="dataset/audio/"):

    # Removing old library file if exists
    if os.path.exists(path + "library.json"):
        os.remove(path + "library.json")

    # Create a list of track ID's contained in the current library
    id_list = set()

    for fold in listdir_nohidden(path):
        filenames = listdir_nohidden(path + fold)
        for f in filenames:
            track_id = f.split(".")
            id_list.add(track_id[0])

    count = len(id_list)

    write_data = dict()
    write_data["recordingNumber"] = str(count)
    write_data["tracks"] = list()

    # Create a list of all metadata files
    meta_files = list()
    for filename in listdir_nohidden("dataset/metadata/"):
        if filename != "library.json":
            meta_files.append(filename)

    # Check each metadata track for presence in library
    found_files = set()
    for f in meta_files:
        page_num = 1
        page = 1

        while page < page_num + 1:

            # Open the json
            with open(
                "dataset/metadata/" + f + "/page" + str(page) + ".json", "r"
            ) as jsonfile:
                data = jsonfile.read()
            data = json.loads(data)
            page_num = data["numPages"]

            # Parse through each track
            for i in range(len(data["recordings"])):
                track = data["recordings"][i]["id"]
                if track in id_list:
                    track_info = data["recordings"][i]
                    write_data["tracks"].append(track_info)
            page += 1

    # Retrieves information from  API for tracks that cannot be found in the
    # currently saved metadata
    found_files = list()
    for i in range(len(write_data["tracks"])):
        found_files.append(write_data["tracks"][i]["id"])

    not_found = list(set(id_list) - set(found_files))

    for i in not_found:
        track_find = "nr:" + i
        path = metadata([track_find])
        with open(path + "/page1.json") as jsonfile:
            data = jsonfile.read()
        data = json.loads(data)
        write_data["tracks"].append(data["recordings"][0])

    with open("data.txt", "w") as outfile:
        json.dump(write_data, outfile)

    os.rename("data.txt", "dataset/metadata/library.json")


def main():
    act = sys.argv[1]
    params = sys.argv[2:]

    if act == "-m":
        metadata(params)

    elif act == "-dl":
        download(params)

    elif act == "-p":
        purge(int(params[0]))

    elif act == "-g":
        if len(params) == 1:
            gen_meta(params[0])
        else:
            gen_meta()

    elif act == "-d":
        dec = input(
            "Are you sure you want to proceed with deleting? (Y or N)\n"
        )
        if dec == "Y":
            delete(params)

    else:
        print(
            "The command entered was not found, please consult the README for instructions and available commands."
        )


# Handles command line execution
if __name__ == "__main__":
    main()

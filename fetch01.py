# -*- coding: utf-8 -*-
'''
1. change the the name of the eth which used for connecting left/right camera to "wirelessconnect0"
2. connect wirelessconnect0 to hotspot "cameraleft" & "cameraright", with password remembered.
3. the first 3 images are used for time calibration, so keep it aligned.
4. ensure the capture interval > 5sec. 
5. request admin permission for eth ctrl.
6. request exitpy module from git hub
	#exif.py required. <https://github.com/ianare/exif-py/releases>
7. fisheye dewarp binary required for running.
'''
import urllib.request  
import re  
import os
import sys
import time
import binascii
import socket
import json
import exifread
import time
import signal
import threading
import logging
import shutil


#---------------------------------------------------

DEBUG=False

leftHostname = "http://cameraleft/DCIM/101MSDCF"
rightHostname = "http://cameraright/DCIM/101MSDCF"


'''
logging.basicConfig(
    level=logging.INFO,
    format='(thread[%(thread)s:%(threadName)s]: %(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s')
'''
logging.basicConfig(
    level=logging.INFO,
    format='(thread[%(thread)s:%(threadName)s]: %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s')


#---------------------------------------------------
gRequestExit = False;
gDriftRange = 4; # sec

workingDir = os.getcwd();

if len(sys.argv) >=2:
    workingDir = sys.argv[1]

logging.info("workingDir: %s", workingDir);

imageListRecordFile = "imageList.json"
dropLeftImageFile = "leftDropped.json"
leftImageDir = os.path.join(workingDir, "Left");
rightImageDir = os.path.join(workingDir, "Right");
outputImageDir = os.path.join(workingDir, "Output");

combExePath = os.path.join(workingDir,"calibration_pipeline_main","calibration_pipeline_main.exe")
equiPath = os.path.join(workingDir,"equi_3570_3570_170_170")

#---------------------------------------------------

#left: True for left, False for right
#enable: True for open, False for close
def enableWirelessConnect(left, enable=True):
    #cmd = r'netsh interface set interface name="wirelessconnect3" admin=enabled'
    
    if left:
        cmd = r'netsh wlan connect ssid=cameraleft name=cameraleft interface="wirelessconnect0"'
    else:
        cmd = r'netsh wlan connect ssid=cameraright name=cameraright interface="wirelessconnect0"'

    logging.debug("Execute cmd:  %s", cmd)
    output = os.popen(cmd)
    logging.debug("        result: %s", str(output))
    time.sleep(10)



'''
#use PHONE AP
'''
#hostname = "http://cameraleft/DCIM/101MSDCF"
def fetchImagesFromCamera(hostname, imagedir, threadid):
    if not os.path.isdir(imagedir):
        os.mkdir(imagedir)

    recordFile = os.path.join(imagedir, imageListRecordFile);

    filesTransfered = []
    fileList = []
    filesTransfered = parseImageRecordFile(recordFile, True)

    socket.setdefaulttimeout(300)

    resultLast = None;
    while True:
        logging.debug("Looping : ")
        try:
            req = urllib.request.Request(hostname)
            webpage = urllib.request.urlopen(req)
            content = webpage.read()

            result = re.findall(r'(fname[^\s]*?.(JPG|jpg))',str(content))
            if result == resultLast:
                logging.info("No change on device, wait ...");
                time.sleep(5);
                continue

            picNameList = [item[0].replace("fname\":\"","") for item in result]
            picNameList.sort();
                           
            for picName in picNameList:
                fileList = [f[0] for f in filesTransfered] #update the searched list.
                
                if picName in fileList:
                    logging.debug( picName + " already exist. skip")
                else:
                    imageurl = hostname + "/" + picName
                    savedFile = os.path.join(imagedir, picName)
                    if True:
                        logging.info("Fetch image: ")
                        logging.info("        From:  " + imageurl);
                        logging.info("        To:    " + savedFile);
                        logging.info("        Start: " + time.strftime('%Y-%m-%d-%H:%M:%S', time.localtime(time.time())))
                    urllib.request.urlretrieve(imageurl, savedFile)
                    if True:
                        logging.info("        Stop:  " + time.strftime('%Y-%m-%d-%H:%M:%S', time.localtime(time.time())) + "\n")

                    imageTime = getJpegTime(savedFile)
                    #imageTime = time.strftime('%Y:%m:%d %H:%M:%S', time.localtime(time.time())) #######

                    if imageTime is None:
                        logging.error("Error: fail to get jpeg timestamp")
                        continue;
                    
                    filesTransfered.append([picName, imageTime])

                    with open(recordFile,'w') as file_object:
                        json.dump(filesTransfered, file_object)
                        logging.debug(filesTransfered)
            resultLast = result
        except Exception as e:
            logging.error("Exception: %s", e)
        
'''
#use SD AP
'''
def fetchAllImages():
    maxCount = 4;
    while not gRequestExit:
        logging.info("Fetch images from left");
        enableWirelessConnect(left=True)
        fetchImagesFromCamera_oneShot(leftHostname, leftImageDir, maxCount)

        logging.info("Fetch images from right");
        enableWirelessConnect(left=False)
        fetchImagesFromCamera_oneShot(rightHostname, rightImageDir, maxCount)
        

def fetchImagesFromCamera_oneShot(hostname, imagedir, maxCount):
    if not os.path.isdir(imagedir):
        os.mkdir(imagedir)

    recordFile = os.path.join(imagedir, imageListRecordFile);

    filesTransfered = []
    fileList = []
    filesTransfered = parseImageRecordFile(recordFile, True)

    socket.setdefaulttimeout(300)

    resultLast = None;
    cnt = 0
    while cnt < maxCount:
        logging.debug("Looping : ")
        try:
            cnt = cnt + 1  #for outloop, use the same retry count as internal count for simplicity
            req = urllib.request.Request(hostname)
            webpage = urllib.request.urlopen(req)
            content = webpage.read()

            logging.info("http access success");
            
            result = re.findall(r'(fname[^\s]*?.(JPG|jpg))',str(content))
            if result == resultLast:
                logging.info("No change on device, wait ...");
                time.sleep(30) ## FIXME
                return

            cnt = 0 #reset cnt, before process new file list
            for picName,postfix in result:
                if cnt >= maxCount:
                    logging.debug("maxCount reached, yield")
                    return

                logging.error('-----');
                
                picName = picName.replace("fname\":\"","");
                fileList = [f[0] for f in filesTransfered] #update the searched list.
                
                if picName in fileList:
                    logging.debug( picName + " already exist. skip")
                else:
                    cnt = cnt + 1
                    imageurl = hostname + "/" + picName
                    savedFile = os.path.join(imagedir, picName)
                    if True:
                        logging.info("Fetch image: ")
                        logging.info("        From:  " + imageurl);
                        logging.info("        To:    " + savedFile);
                        logging.info("        Start: " + time.strftime('%Y-%m-%d-%H:%M:%S', time.localtime(time.time())))
                    urllib.request.urlretrieve(imageurl, savedFile)
                    if True:
                        logging.info("        Stop:  " + time.strftime('%Y-%m-%d-%H:%M:%S', time.localtime(time.time())) + "\n")

                    imageTime = getJpegTime(savedFile)
                    #imageTime = time.strftime('%Y:%m:%d %H:%M:%S', time.localtime(time.time())) #######

                    if imageTime is None:
                        logging.error("Error: fail to get jpeg timestamp")
                        continue;
                    
                    filesTransfered.append([picName, imageTime])

                    with open(recordFile,'w') as file_object:
                        json.dump(filesTransfered, file_object)
                        logging.debug(filesTransfered)

            resultLast = result
            cnt = maxCount + 1 # exit current loop directly, as all file list processed.
        except Exception as e:
            logging.error("Exception: %s", e)
            time.sleep(10)
        

def getJpegTime(jpegfile):
    logging.debug("check time for jpegfile: " + jpegfile)
    with open(jpegfile, 'rb') as f:
        tags = exifread.process_file(f);
        logging.debug("getJpegTime return: " + str(tags['EXIF DateTimeOriginal']))
        return str(tags['EXIF DateTimeOriginal'])
    return None;


def parseImageRecordFile(recordFile, removeIfException=False):
    fileList = []
    if os.path.exists(recordFile):
        try:
            with open(recordFile,'r') as file_object:
                fileList = json.load(file_object)
                logging.debug(fileList)
        except Exception as e:
            logging.error("Exception: %s", e)
            fileList = []
            if removeIfException:
                os.remove(recordFile);
    else:
        logging.warning("No transfered file list found in " + recordFile);
    return fileList



# String时间转换为long
def timeStampTransform(timeStr):
    # 将其转换为时间数组
    timeArray = time.strptime(timeStr,'%Y:%m:%d %H:%M:%S')
    # 转换为时间戳
    timeStamp = int(time.mktime(timeArray))
    return timeStamp


def findMatchingRightFile(left, rightListTodo, deltaStd, driftRange):
    lefttime=timeStampTransform(left[1])
    righttimeList = [timeStampTransform(item[1]) for item in rightListTodo]
    diffList = [abs(lefttime-item-deltaStd) for item in righttimeList]
    for i in range(len(diffList)):
        if diffList[i] <= driftRange:
            return rightListTodo[i]
    return None




#fullList: [["imagename", imagetime], ["imagename", imagetime], [,], ...]
#doneList: ["imagename"", "imagename", ...]
#return: [["imagename", imagetime], ["imagename", imagetime], [,], ...]
def getUnprocessedList(fullList, doneList):
    unprocessedList = []
    for i in range(len(fullList)):
        if fullList[i][0] not in doneList:
            unprocessedList.append(fullList[i])
    logging.debug("Found unprocessed image list: " + str(unprocessedList))
    return unprocessedList




#================================

def getFileNameAndExt(filename):
    (filepath,tempfilename) = os.path.split(filename);
    (shotname,extension) = os.path.splitext(tempfilename);
    return shotname,extension

def processLeftRight(left, right):
    
    leftFullPath=os.path.join(leftImageDir, left[0]);
    rightFullPath=os.path.join(rightImageDir, right[0]);
    outFullPath=os.path.join(outputImageDir, left[0]); #reuse the left file name for simplicity

    tempFullPath=os.path.join(workingDir, "tmporary");
    
    
    return left[0] ##FIXME


def processLeftRight(leftitem, rightitem):
    left=leftitem[0]
    right=rightitem[0]
    comb_name=getFileNameAndExt(left)[0] + "_" + right 
    output = "comb0_3780_180x180_3dh_LR" + "__" + comb_name;
    
    logging.info("Process image. left %s. right: %s. output: %s", leftitem, rightitem, output);
    leftFullPath=os.path.join(leftImageDir, left);
    rightFullPath=os.path.join(rightImageDir, right);
    outFullPath=os.path.join(outputImageDir, output); #reuse the left file name for simplicity

    tempFullPath=os.path.join(workingDir, "tmporary");
    tempLeftPath=os.path.join(tempFullPath,"left");
    tempRightpath=os.path.join(tempFullPath,"right")
    tempOutputPath = os.path.join(tempFullPath,"equi_3570_3570_170_170",output)

    # creat source file
    if os.path.exists(tempFullPath):
        shutil.rmtree(tempFullPath)
    if not os.path.exists(tempFullPath):
        os.mkdir(tempFullPath)
    if not os.path.exists(tempLeftPath):
        os.mkdir(tempLeftPath)
    if not os.path.exists(tempRightpath):
        os.mkdir(tempRightpath)
    if os.path.exists(tempLeftPath) and os.path.exists(tempRightpath):
        shutil.copy(leftFullPath, tempLeftPath)
        shutil.copy(rightFullPath, tempRightpath)
    else:
        logging.error("mkdir fail!!!")
        return None
    
    # exe combine pic
    os.system(combExePath + r' -r 3570 -m "name_order" -i ' + tempFullPath + ' -c ' + equiPath)
    #move result to target folder
    shutil.move(os.path.join(tempFullPath,"equi_3570_3570_170_170","comb0_3780_180x180_3dh_LR.jpg"),outFullPath)
    #time.sleep(9999)
    return output

#================================

def postProcessImage(leftdir, rightdir, outputdir):
    if not os.path.isdir(outputdir):
        os.mkdir(outputdir)
    leftFile = os.path.join(leftdir, imageListRecordFile);
    rightFile = os.path.join(rightdir, imageListRecordFile);
    outputFile = os.path.join(outputdir, imageListRecordFile);
    droppedFile = os.path.join(outputdir, dropLeftImageFile);

    deltaStd = 0;
    driftRange = gDriftRange; # sec
    while not gRequestExit:
        leftList = parseImageRecordFile(leftFile)
        rightList = parseImageRecordFile(rightFile)
        if len(leftList) <3 or len(rightList) <3:
            logging.info("Input image file num: left %d, right %d, wait 30sec", len(leftList), len(rightList))
            time.sleep(30)
            continue
        #leftStdHead = leftList[0:3]
        #rightStdHead = rightList[0:3]
        
        leftTimeList = [timeStampTransform(info[1]) for info in leftList]
        rightTimeList = [timeStampTransform(info[1]) for info in rightList]

        deltaTimeList = [leftTimeList[i] - rightTimeList[i] for i in [0,1,2]]
        deltaStd = sum(deltaTimeList)/3
        logging.info("deltaTimeList = " + str(deltaTimeList));

        verifyList = [deltaTimeList[i] - deltaStd for i in [0,1,2]]
        for i in verifyList:
            if abs(i) > 10:
                logging.error("Invalid std imagelist for time:")
                logging.error("        left:  %s", str(leftTimeList[0:3]))
                logging.error("        right: %s", str(rightTimeList[0:3]))
                sys.exit(0)
        break;

    logging.info("Using std delta time: %d, drift range: %d", deltaStd, driftRange);

    '''
    matching strategy:
    1. get left, right, output file list
    2. loop all left files, get the unprocess files that not in output.
    3. loop all right files, get the unprocess files that not in output.
    4. if any of above two lists is empty, wait 50sec before next loop; #assuming that fetching 1 image cost ~60sec
    5. loop unprocessed left files
           check whether existed in dropped list:
                if yes:
                      continue
           find the matching left one.
           if not found:
                print log, and append to dropped file list
                dump to dropped file.
                continue for next loop
            else
                 process
                 if success:
                     append to output file list.

    '''
    while not gRequestExit:
        try:
            leftList = parseImageRecordFile(leftFile)  #[["imagename","time"], ["imagename","time"], ...]
            rightList = parseImageRecordFile(rightFile)  #[["imagename","time"], ["imagename","time"], ...]
            outputList = parseImageRecordFile(outputFile)  #[["imagename","leftimage", "rightimage"], ["imagename","leftimage", "rightimage"], ...]
            droppedList = parseImageRecordFile(droppedFile);  #["imagename", "imagename", ...]

            leftProcessedList = [item[1] for item in outputList]
            rightProcessedList = [item[2] for item in outputList]
            
            leftListTodo = getUnprocessedList(leftList, leftProcessedList)  #[["imagename","time"], ["imagename","time"], ...]
            rightListTodo = getUnprocessedList(rightList, rightProcessedList)
            if len(leftListTodo) == 0 or len(rightListTodo) == 0:
                logging.info("source image list not ready: left num = %d, right num = %d", len(leftListTodo), len(rightListTodo));
                time.sleep(60)
                continue
            
            for left in leftListTodo:
                if left[0] in droppedList:
                    logging.debug("Left image already existed in dropped list: %s", left[0])
                    continue  #continue for loop
                
                right = findMatchingRightFile(left, rightListTodo, deltaStd, driftRange)
                if right is None:
                    logging.warning("Fail to find matching image for left: %s. append to dropped list.", str(left));
                    droppedList.append(left[0])
                    with open(droppedFile,'w') as file_object:
                        json.dump(droppedList, file_object)
                        continue  #continue for loop

                outName = processLeftRight(left, right);
                    
                if outName is not None and outName != "":
                    logging.info("Generate output: %s; left: %s ; right: %s", outName, str(left), str(right))

                    outputList.append([outName, left[0], right[0]])
                    with open(outputFile,'w') as file_object:
                        json.dump(outputList, file_object)
                        #logging.debug(outputList)
            logging.info("ImageProcessing thread done for one loop, wait 60sec for next loop...");
            time.sleep(60);
            
        except Exception as e:
            logging.error("Exception: %s", e)
            traceback.print_exc() 


def signal_handler(sig, frame):
    gRequestExit = True;
    logging.error('Caught signal: %s. Request thread quit now ...', sig)
    #sys.exit(0)


if __name__ == "__main__":

    
    #fetchImagesFromCamera(hostname, leftImageDir)

    ## install signal handler, for gracefully shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    threads = []
    
    t=threading.Thread(target=fetchAllImages);
    threads.append(t)
    
    '''
    #use PHONE AP
    t=threading.Thread(target=fetchImagesFromCamera, args=(leftHostname, leftImageDir,0,));
    threads.append(t)
    t=threading.Thread(target=fetchImagesFromCamera, args=(rightHostname, rightImageDir,1,));
    threads.append(t)
    '''
    '''
    #use SD AP
    '''

    
    t=threading.Thread(target=postProcessImage, args=(leftImageDir, rightImageDir, outputImageDir,));
    threads.append(t);
    
    
    for t in threads:
        t.setDaemon(True)
        t.start()


    while not gRequestExit:
        for t in threads:
            if not t.isAlive():
                break;
        time.sleep(5)

    for t in threads:
        t.join()


    logging.info("All threads exit");

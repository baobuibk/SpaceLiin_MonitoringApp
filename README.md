# SpaceLiin_MonitoringApp

## App:
https://www.mediafire.com/file/6kmbl4bwv9dvo23/app.zip/file
![image](https://github.com/user-attachments/assets/ea945204-87f9-49db-9a06-9d6c8aabb463)

## Install:
### Python Code:
***Set-up***

```shell
git clone https://github.com/baobuibk/SpaceLiin_MonitoringApp.git
cd $your_clone_folder
```
```shell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt.
```
***Run:***
```shell
python ./qt_app.py
```
### With downloaded app:
`Run the qt_app.exe`

## Usage:
### Mode RS422:
![image](https://github.com/user-attachments/assets/46782ebd-9ee5-4aaf-8658-bd2a237f2e22)

In RS422 mode, 282 bytes are continuously run into the buffer. If you know that data is coming but not showing, simply click the mode change button until you get the correct frame. This action clears the buffer, allowing you to catch the beat.

### Mode RF:
Choose right serial port, then start.

### Command:
You can send commands when auto report is enabled, but you won't be able to see the response of the command. If you want to see the response, you must click "Auto Report Stop". After that, you will be able to see the response of the command.

You can click on any command in the left table to copy it to the clipboard, then paste it into the command line. Instead of clicking, if you simply move the cursor to a line containing a command, it will display a description of what that command does.

![image](https://github.com/user-attachments/assets/4744877b-cb82-4e86-a8f4-7c1464634b78)



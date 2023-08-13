"""
iCloud重复照片清理工具

该脚本连接到两个iCloud账户，检索每个账户中所有照片的ID，找出两个账户之间的重复照片ID，并从一个账户中删除重复照片。

背景:
因为使用了苹果新出的 "共享图库" 功能(此功能可以将多个账户的图库共享显示)
后来因为某些原因停止使用此功能(原因包括icloud网页崩溃,第三方的图库同步脚本失灵,同步到GooglePhotos时存储空间给我算多次等等)
然后退出共享图库的时候,
    操作退出的账户:account2,让用户确认了是否保留共享出来的照片(我选了不保留)
    但是其他账户:account1,并没有让选择是否保留(默认保留,这逻辑有问题吧库克!)
    最终导致结果是
      account2退出之后只保留了account2的账号
      account1因为保留了所有的照片,包含account1与account2的
      account1的照片重复了!!!
所以有了这个脚本
该脚本连接到两个iCloud账户，检索每个账户中所有照片的ID，找出两个账户之间的重复照片ID，并从一个账户中删除重复照片。




要求：
- pyicloud库（使用命令 'pip install pyicloud' 安装）
  因为使用的是中国大陆的iCloud账户,所以使用的是魔改版的pyicloud
- tqdm库（使用命令 'pip install tqdm' 安装）

使用方法：
1. 将 'account1_email' 和 'account1_password' 替换为您的第一个iCloud账户凭据。
2. 将 'account2_email' 和 'account2_password' 替换为您的第二个iCloud账户凭据。
3. 运行脚本以清除其中一个账户中的重复照片。

"""

from pyicloud import PyiCloudService
from tqdm import tqdm


def get_all_photo_id(account_api):
    """
    获取账户下所有照片的id
    """
    photos = account_api.photos.all
    # 初始化一个空的 set 来存储照片文件名
    photo_id_set = set()
    for photo in tqdm(photos, desc=f"{account_api.user['accountName']}\t盘点中,请稍后", unit="个"):
        photo_id_set.add(photo.id)
    return photo_id_set


def del_photo_by_id(account_api, ids):
    photos = account_api.photos.all
    for photo in tqdm(photos, desc=f"{account_api.user['accountName']}\t删除中,请稍后", unit="个"):
        if photo.id in ids:
            photo.delete()


# 初始化两个 iCloud 账户的 API 实例
account1_api = PyiCloudService("account1_email", "account1_password", china_mainland=True)
account2_api = PyiCloudService("account2_email", "account2_password", china_mainland=True)

# 获取两个账户的照片 ID
account1_ids = get_all_photo_id(account1_api)
account2_ids = get_all_photo_id(account2_api)

# 找出两个账户中重复的照片 ID
duplicate_ids = account1_ids.intersection(account2_ids)

# 在第一个账户中删除重复的照片
del_photo_by_id(account1_api, duplicate_ids)

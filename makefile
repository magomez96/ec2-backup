install:
	/usr/sbin/pkg_add ftp://ftp.netbsd.org/pub/pkgsrc/packages/NetBSD/i386/7.0/All/python36-3.6.5.tgz
	/usr/sbin/pkg_add ftp://ftp.netbsd.org/pub/pkgsrc/packages/NetBSD/i386/7.0/All/py36-pip-9.0.3.tgz
	/usr/pkg/bin/pip3.6 install -r src/requirements.txt
	/bin/mkdir -p /usr/local/bin
	/bin/cp src/ec2-backup.py /usr/local/bin/ec2-backup.py
	/bin/cp src/ec2-backup /usr/local/bin/ec2-backup
	/bin/chmod +x /usr/local/bin/ec2-backup
